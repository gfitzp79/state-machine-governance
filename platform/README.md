# State Machine Governance — Reference Implementation

An open-source GRC platform that enforces the [state machine governance
framework](../README.md) natively. Modular, object-oriented, dockerised.

This is not a spreadsheet with a web front end. Governance here is a set of
interconnected state machines: every lifecycle transition is gated, every hard
rule is an invariant checked before commit, and a state change in one entity
propagates to every entity it affects.

## Install

Requires Docker with Compose v2. Nothing else: no Python, Node or PostgreSQL on
the host.

```bash
git clone https://github.com/gfitzp79/state-machine-governance.git
cd state-machine-governance/platform
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8080> and sign in as `analyst@example.com` /
`changeme123`. First boot builds the images, creates the schema, installs the
immutability triggers and seeds a demo dataset.

Change `JWT_SECRET` in `.env` before this is reachable by anyone but you:

```bash
openssl rand -hex 32
```

## Make it yours

Your operating model lives in [`config/governance.yml`](./config/governance.yml),
not in the code. Risk appetite bands, acceptance windows, control families,
roles, compliance frameworks, escalation SLAs — everything the specification
marks `[CUSTOMISE]` — is configuration.

```bash
$EDITOR config/governance.yml
docker compose restart api
```

The file is bind-mounted rather than baked into the image, so there is nothing to
rebuild. It is validated strictly at boot: a rating band that leaves a score
unrated, or a `CE-Unvalidated` rating configured to buy a likelihood reduction,
stops the API from starting rather than silently scoring risks against a broken
model.

Full guide: [docs/CONFIGURATION.md](./docs/CONFIGURATION.md).

---

## What "enforced" means here

Three things are true of every rule in this system, and they are what separate it
from configuration:

**Gates refuse, and say why.** A transition that cannot happen returns HTTP 409
with every precondition it evaluated, each identified by its specification
reference. The UI renders that list directly, so "why can't I advance this?" is
answered on screen rather than in a support ticket.

**Invariants run before commit, on every write path.** Not in the UI, not in one
service method — in the invariant registry, evaluated on every write to the
entity regardless of which endpoint reached it.

**The schema backs the service layer.** `CHECK` constraints, conditional
`NOT NULL`s and immutability triggers mean a direct `psql` session cannot create
an open-ended risk acceptance, accept a Critical threat scenario, or edit the
audit log. The smoke test proves this by trying.

### The cascade

The clearest demonstration ships in the seed data. `CTL-001` (MFA on privileged
access) is Operating. It reduces `RISK-001` from Critical to High, and it
mitigates `THR-001` in threat model `TM-001`, which is Active with dual sign-off.

Open `CTL-001`, open deployment `DEP-002`, record a **failing** control test. In
one transaction:

| | before | after |
|---|---|---|
| `DEP-002` | Active | **Failed** |
| `CTL-001` | Operating | **Failure** (DL-1 propagation) |
| `RISK-001` residual | unlocked, 15 High | **re-locked** (CINV-5) |
| `RISK-001` reported score | 15 High | **20 Critical** — reverts to inherent (RES-2) |
| `THR-001` | Mitigated | **Identified** — re-opened (TINV-4) |
| `TM-001` | Active, dual sign-off | **Review**, both signatures stripped (TINV-2) |

Nobody clicked six buttons. One piece of evidence changed, and every conclusion
that rested on it was withdrawn.

---

## Architecture

```
platform/
├── docker-compose.yml          postgres + fastapi + nginx
├── config/
│   └── governance.yml          your operating model, bind-mounted and hot-reloadable
├── docs/
│   └── CONFIGURATION.md        how to align the platform to your framework
├── backend/
│   └── app/
│       ├── engine/             the framework, domain-agnostic
│       │   ├── state_machine.py   declarative lifecycles, gates, preconditions
│       │   ├── invariants.py      the invariant registry
│       │   ├── scoring.py         deterministic 5x5 scoring engine
│       │   ├── cascade.py         cross-lifecycle event bus
│       │   └── audit.py           immutable trail + notifications
│       ├── core/
│       │   ├── governance.py      loads and validates config/governance.yml
│       │   └── service.py         the single write path every module shares
│       ├── modules/            one package per domain
│       │   ├── risk/           models · machine · invariants · service · router
│       │   ├── control/        objective → activity → deployment
│       │   ├── policy/         policies, standards, exceptions
│       │   ├── treatment/
│       │   ├── threat/         STRIDE models bound to GRC state
│       │   ├── cascades.py     every cross-module propagation, in one file
│       │   └── jobs.py         the time-based invariants
│       └── seed.py
└── frontend/                   React · TypeScript · Tailwind, served by nginx
```

### The engine

`app/engine/` knows nothing about risk, controls or policy. It provides four
primitives that every module composes:

**`StateMachine`** — a lifecycle declared as states plus gated edges. Each edge
names its gate, its preconditions (each with a specification ID), the roles
permitted to fire it, and the cascade events it emits. `fire()` is the only
sanctioned way to change a lifecycle field anywhere in the codebase.

```python
Transition(
    source="Evidence_Residual",
    target="Monitoring",
    gate="GATE_RESIDUAL_VALIDATED",
    roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
    preconditions=(
        Precondition("RESIDUAL.1", "Mitigations fully implemented", _treatments_complete,
                     "Every linked treatment must be Complete. Planned mitigations do "
                     "not reduce residual risk (RINV-9)."),
        ...
    ),
    cascades=("risk.monitoring_started",),
)
```

**`InvariantRegistry`** — each invariant carries its ID, the rule in plain
English, its enforcement layer, its mechanism, its violation behaviour, and its
specification reference. `/api/engine/invariants` serves the live catalogue, and
the Engine page in the UI renders it straight from the running registry.

**`ScoringEngine`** — stateless and deterministic. Resolves control effectiveness
through objective → activity → deployment, discarding everything that does not
qualify and returning the reason for each exclusion. Worst case across qualifying
deployments, never an average, never best case.

**`CascadeBus`** — handlers registered per event, running inside the caller's
transaction so state change, propagation and audit commit atomically or not at
all. Every effect is returned to the caller, so the API response tells you what
else changed.

### The one write path

`LifecycleService` gives every module the same four steps in the same order, and
routers never touch the session directly:

1. **mutate** — apply the caller's change
2. **enforce** — run every invariant registered for the entity
3. **cascade** — propagate to related entities
4. **audit** — record it, including the full gate evaluation

Adding a module means writing `models.py`, `machine.py`, `invariants.py`,
`service.py`, `router.py`. The enforcement behaviour comes from the base class.

---

## What is implemented

**8 state machines · 53 gated transitions · 40 invariants · 23 cascade events**

| Lifecycle | States | Source |
|---|---|---|
| Risk | 7 phases + Closed | state-transitions §1 |
| Control objective | Design → Implementation → Operating ⇄ Failure ⇄ Redesign → Deprecated | §2 |
| Control activity | Draft → Active ⇄ Suspended → Retired | §3 |
| Control deployment | Planned → Active ⇄ Degraded ⇄ Failed → Decommissioned | §4 |
| Policy | Draft → Under_Review → Approved → Active ⇄ Under_Revision → Deprecated | §5 |
| Policy exception | Requested → Approved → Expired / Rejected | §6 |
| Treatment | Proposed → Validated → Approved → In_Progress → Complete | §5.2 |
| Threat model | Scope → Decomposition → Threat_Analysis → Mitigation_Design → Review ⇄ Active | §7 |

Invariants: **RINV-1..13**, **CINV-1..10**, **PINV-1..9**, **TINV-1..6**, plus
SEP-1 and PE-5. Every one is listed at `/api/engine/invariants` with its
enforcement layer and mechanism.

### Enforced at the database layer

Append-only tables, guarded by triggers that reject `UPDATE` and `DELETE`
regardless of how the row is reached: `audit_log`, `risk_phase_history`,
`policy_versions`, `control_tests`, `treatment_checkins`.

Named `CHECK` constraints that back service-layer rules, including
`ck_risks_acceptance_time_bound` (RINV-4), `ck_risks_critical_never_accepted`
(RINV-5), `ck_risks_sep1_owner_not_stakeholder`, `ck_policies_no_self_approval`
(PINV-5), `ck_control_deployments_ce_evidence_required` (CINV-1) and
`ck_threat_scenarios_no_local_acceptance_above_low` (TINV-3).

### The time-based invariants

Rules that cannot be enforced per-transaction, because nothing happens at the
moment they become true. `POST /api/engine/jobs/run` (or the **Run scheduled
jobs** button) executes them and reports what fired:

- **CINV-10** expired control effectiveness auto-downgrades to CE-Unvalidated
- **RINV-11** expired acceptances escalate; no silent expiry
- **PE-4 / PE-5** exception expiry notification and governance-gap flagging
- **CINV-5** control failures persisting past 15 business days escalate
- Risk review SLA tracking

In production these run on a scheduler. Exposing them as an endpoint makes them
observable and testable rather than invisible background behaviour.

---

## Verifying it

The smoke test walks every claim above against a live API, including the full
cascade and direct-SQL attempts to bypass the service layer.

```bash
docker compose exec api python config_test.py     # 32 tests: the configuration layer
docker compose exec api python smoke_test.py      # 80 tests: the enforcement layer
```

`config_test.py` proves both halves of configurability: that invalid governance
models are refused at boot, and that valid changes actually take effect.

`smoke_test.py` mutates state deliberately — failing a control test is the point
— so it needs a freshly seeded database and refuses to start otherwise:

```bash
docker compose down -v && docker compose up -d
docker compose exec api python smoke_test.py
```

Expect **32 passed** and **80 passed**, zero failures.

---

## Demo accounts

Password for all: `changeme123`. Roles determine which transitions you can fire,
so sign in as different people to see the gates behave differently.

| Email | Who | Roles |
|---|---|---|
| `analyst@example.com` | Priya Raman | Risk_Analyst |
| `grc@example.com` | Tomas Lindqvist | GRC_Engineer |
| `ciso@example.com` | Marcus Bell | CISO, Risk_Stakeholder |
| `control@example.com` | Jonah Weiss | Control_Owner, Control_Operator |
| `appsec@example.com` | Ines Ferreira | AppSec_Lead, Security_SME |
| `sysowner@example.com` | Dmitri Sokolov | System_Owner, Risk_Owner |
| `owner@example.com` | Elena Vasquez | Risk_Owner |
| `delivery@example.com` | Sam Okonkwo | Risk_Treatment_Owner |
| `policy@example.com` | Aoife Byrne | Policy_Owner |
| `admin@example.com` | Ada Okafor | Admin, GRC_Engineer |

Other things worth trying:

- **RISK-002** sits at the residual gate with three of five conditions met. The
  gate panel shows exactly what is missing and why each condition exists.
- **RISK-003** is Critical. Try to accept it (RINV-5).
- **POL-002** is Active with linked controls. Remove them all (PINV-1).
- **POL-003** is a draft. Try approving it as its own owner (PINV-5).
- **TRT-003** is unvalidated. Try to commit as someone other than its owner.
- **DEP-006** has evidence more than a year old. Run the scheduled jobs (CINV-10).

---

## Configuration

Everything is environment-driven, so the same image runs unchanged from
docker-compose to a managed cloud deployment.

Two separate concerns, deliberately kept apart.

**`.env` is infrastructure.** Where the database is, what the secret is, which
port to serve on.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local postgres | Point at managed PostgreSQL for cloud |
| `JWT_SECRET` | `dev-secret-change-me` | **Change this.** `openssl rand -hex 32` |
| `JWT_TTL_MINUTES` | `720` | Session lifetime |
| `SEED_DEMO_DATA` | `true` | Set `false` for a real deployment |
| `CORS_ORIGINS` | `http://localhost:8080` | Comma-separated; must match how the UI is reached |
| `WEB_PORT` | `8080` | Host port for the UI |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `grc` | Database credentials |
| `GOVERNANCE_CONFIG_FILE` | `./config/governance.yml` | Point at your own file to keep it outside the checkout |

**`config/governance.yml` is your operating model.** Appetite, taxonomy, roles,
SLAs. See [docs/CONFIGURATION.md](./docs/CONFIGURATION.md).

### Going to production

This is a reference implementation. Before it carries real governance data:

- Set `SEED_DEMO_DATA=false` and generate a real `JWT_SECRET`.
- Replace local password auth with your OIDC provider. `app/core/security.py` is
  the only file that changes: map group claims onto the same role list and
  everything downstream is unaffected.
- Terminate TLS in front of nginx.
- Run the scheduled jobs on a real scheduler rather than the endpoint.
- Take the [AI tool lifecycle model](../architecture/ai-tool-lifecycle.md)
  seriously. A tool without a named owner does not advance to Build; a tool
  without prompt telemetry in the SIEM does not enter Production.

---

## Known limitations

**Schema migrations.** The schema is created with `create_all` on first boot and
stamped with the immutability triggers. That is correct for a fresh install, but
there is no migration path between versions yet. Upgrading today means exporting
your data, recreating the schema and re-importing. Alembic is the next
infrastructure task.

**Vendor and third-party risk** (data-model §7) is specified but not built. The
engine makes it a follow-on module rather than a rework: the same five files as
any other domain.

**Authentication** is local password auth. OIDC is a single-file change — see
above — but it is not wired to a provider out of the box.

---

## Licence

The reference implementation in this directory is licensed under the
**Apache License 2.0**. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

The governance framework it implements — the specification, architecture and
methodology documents in the parent directory — is released separately under
**CC BY 4.0**. See the [repository root](../README.md) and
[DISCLAIMER](../disclaimer.md).

The two are licensed differently on purpose: CC BY 4.0 suits the documents, and
Creative Commons advises against applying its licences to software.
