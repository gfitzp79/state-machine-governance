# State Machine Governance: Reference Implementation

An open-source GRC platform that enforces the [state machine governance
framework](../README.md) natively. Modular, object-oriented, dockerised.

This is not a spreadsheet with a web front end. Governance here is a set of
interconnected state machines: every lifecycle transition is gated, every hard
rule is an invariant checked before commit, and a state change in one entity
propagates to every entity it affects.

**This directory implements a specification; it does not define one.** The rules
live in [`specification/codified-rules.md`](../specification/codified-rules.md),
their lifecycles in
[`state-transitions.md`](../specification/state-transitions.md), and their
enforcement layers in
[`invariants-catalogue.md`](../specification/invariants-catalogue.md). Every
invariant registered below carries a `spec_ref` back to the section that
justifies it, and CI fails if one points at a section that does not exist. Where
the code and the specification disagree, the specification is right. The
repository root has a [worked example](../README.md#one-rule-end-to-end) that
follows one rule from the specification through to the test that proves it.

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
roles, compliance frameworks, escalation SLAs: everything the specification
marks `[CUSTOMISE]` is configuration.

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
service method, but in the invariant registry, evaluated on every write to the
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
| `RISK-001` reported score | 15 High | **20 Critical**: reverts to inherent (RES-2) |
| `THR-001` | Mitigated | **Identified**: re-opened (TINV-4) |
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
│       │   ├── compliance/     frameworks, requirements, the Statement of Applicability
│       │   ├── cascades.py     every cross-module propagation, in one file
│       │   └── jobs.py         the time-based invariants
│       └── seed.py
└── frontend/                   React · TypeScript · Tailwind, served by nginx
```

### The engine

`app/engine/` knows nothing about risk, controls or policy. It provides four
primitives that every module composes:

**`StateMachine`**: a lifecycle declared as states plus gated edges. Each edge
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

**`InvariantRegistry`**: each invariant carries its ID, the rule in plain
English, its enforcement layer, its mechanism, its violation behaviour, and its
specification reference. `/api/engine/invariants` serves the live catalogue, and
the Engine page in the UI renders it straight from the running registry.

**`ScoringEngine`**: stateless and deterministic. Resolves control effectiveness
through objective → activity → deployment, discarding everything that does not
qualify and returning the reason for each exclusion. Worst case across qualifying
deployments, never an average, never best case.

**`CascadeBus`**: handlers registered per event, running inside the caller's
transaction so state change, propagation and audit commit atomically or not at
all. Every effect is returned to the caller, so the API response tells you what
else changed.

### The one write path

`LifecycleService` gives every module the same four steps in the same order, and
routers never touch the session directly:

1. **mutate**: apply the caller's change
2. **enforce**: run every invariant registered for the entity
3. **cascade**: propagate to related entities
4. **audit**: record it, including the full gate evaluation

Adding a module means writing `models.py`, `machine.py`, `invariants.py`,
`service.py`, `router.py`. The enforcement behaviour comes from the base class.

---

## What is implemented

**9 state machines · 65 gated transitions · 57 invariants · 28 cascade events**

Nine state machines, one per row, each declared in
`modules/<domain>/machine.py` and specified in the section named beside it.

| Lifecycle | States | Specification |
|---|---|---|
| Risk | 7 phases + Closed | [state-transitions §1](../specification/state-transitions.md#1-risk-lifecycle-7-phases) |
| Control objective | Design → Implementation → Operating ⇄ Failure ⇄ Redesign → Deprecated | [§2](../specification/state-transitions.md#2-control-objective-lifecycle-6-states) |
| Control activity | Draft → Active ⇄ Suspended → Retired | [§3](../specification/state-transitions.md#3-control-activity-lifecycle-4-states) |
| Control deployment | Planned → Active ⇄ Degraded ⇄ Failed → Decommissioned | [§4](../specification/state-transitions.md#4-control-deployment-lifecycle-5-states) |
| Policy | Draft → Under_Review → Approved → Active ⇄ Under_Revision → Deprecated | [§5](../specification/state-transitions.md#5-policy-lifecycle-6-states) |
| Policy exception | Requested → Approved → Expired / Rejected | [§6](../specification/state-transitions.md#6-policy-exception-lifecycle-4-states) |
| Threat model | Scope → Decomposition → Threat_Analysis → Mitigation_Design → Review ⇄ Active → Deprecated, or Abandoned | [§7](../specification/state-transitions.md#7-threat-model-lifecycle-8-states) |
| Treatment | Proposed → Validated → Approved → In_Progress → Complete, or Cancelled | [§8](../specification/state-transitions.md#8-treatment-lifecycle-6-states) |
| Requirement assessment | Not_Assessed → Applicable ⇄ Covered ⇄ Gap ⇄ Compensating, or Not_Applicable | [§9](../specification/state-transitions.md#9-requirement-assessment-lifecycle-6-states) |

Invariants: **RINV-1..13**, **CINV-1..12**, **PINV-1..9**, **TINV-1..11**,
**AINV-1..4** and **AINV-6..10**, plus **SEP-1**, **PE-5** and **TM-PARTIAL**.
That is 57, and it matches the
[invariants catalogue](../specification/invariants-catalogue.md) because CI
compares the two on every push. Every one is listed at
`/api/engine/invariants` with its enforcement layer and mechanism, and the
layer it declares is the layer it actually uses.

AINV-5 is in the catalogue but not in that list, deliberately: it is a `Cascade`
rule, something that must *happen* when a control fails rather than a condition
an entity must satisfy, so it has a handler in `modules/cascades.py` instead of
a predicate in an invariant registry.

### Enforced at the database layer

Append-only tables, guarded by triggers that reject `UPDATE` and `DELETE`
regardless of how the row is reached: `audit_log`, `risk_phase_history`,
`policy_versions`, `control_tests`, `treatment_checkins`,
`threat_scenario_evidence`.

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
docker compose exec api python config_test.py     # 33 tests: the configuration layer
docker compose exec api python smoke_test.py      # 160 tests: the enforcement layer
```

`config_test.py` proves both halves of configurability: that invalid governance
models are refused at boot, and that valid changes actually take effect.

`smoke_test.py` mutates state deliberately, because failing a control test is
the point, so it needs a freshly seeded database and refuses to start otherwise:

```bash
docker compose down -v && docker compose up -d
docker compose exec api python smoke_test.py
```

Expect zero failures. CI asserts the state machine, transition, invariant and
cascade counts published above against the code, and it now asserts each suite
total in the comments above against what that suite actually reports when it
runs, so neither can drift again. The totals used to be restated here as prose
as well, and the two copies disagreed without anyone noticing, which is the
argument for stating a figure once and letting the build hold it to the run.

Two further checks run against the schema rather than the API:

```bash
docker compose exec api alembic check           # models and migrations agree
docker compose exec api python upgrade_test.py  # 8 tests: an 0.1.0 database upgrades cleanly
```

### Checking the code against the specification

These run from the **repository root**, not this directory, and need no Docker
and no running stack. They compare the documents with the code, which is the
half of the argument the smoke test cannot make.

```bash
python tools/check_invariant_drift.py    # every invariant in code has a catalogue row, same layer
python tools/check_spec_references.py    # every spec_ref names a section that exists
python tools/check_em_dashes.py          # the editorial rule, enforced
```

The first two are what make the
[worked example in the repository root](../README.md#one-rule-end-to-end)
checkable rather than aspirational: a rule cannot be enforced in code and absent
from the specification without failing the build.

One more check needs a frontend build first, because `dist/` is not committed:

```bash
cd platform/frontend && npm ci && npm run build
python ../../tools/check_no_inline_script.py dist/index.html
```

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
| `CORS_ORIGINS` | `http://localhost:8080` | Only consulted if something calls the API from another origin. The bundled UI goes through the nginx proxy on the same origin, so in the default topology this is unused. |
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

## Schema migrations

The schema is owned by Alembic. `alembic upgrade head` runs on every boot, so a
container started against an older database brings it forward rather than
running against a schema it does not match.

```bash
docker compose exec api alembic current     # where this database is
docker compose exec api alembic history     # how it got there
docker compose exec api alembic check       # do the models and migrations agree
```

Changing a model means writing a migration:

```bash
docker compose exec api alembic revision --autogenerate -m "what changed"
```

Read what it generated before committing it. Autogenerate is good at columns and
constraints and blind to three things that matter here:

- **triggers.** The append-only tables (CINV-7, PINV-9, TSE-1) are enforced by
  trigger, and autogenerate cannot see one. A migration adding an append-only
  table must add it to `APPEND_ONLY_TABLES` in `app/db_init.py` as well, which is
  the authoritative list and is re-asserted and verified at every boot.
- **data.** A column that gains a `NOT NULL` needs a backfill written by hand.
- **intent.** The generated message is whatever you typed. A governance system's
  migration history gets read by people reconstructing when a rule changed.

**Upgrading from 0.1.0.** That release built its schema with `create_all` and has
no migration history. The first boot on 0.2.0 detects this, stamps the database
at the initial revision rather than replaying it, and carries on. Your data is
untouched. `upgrade_test.py` exercises exactly this path.

## Known limitations

**Vendor and third-party risk** (data-model §7) is specified but not built. The
engine makes it a follow-on module rather than a rework: the same five files as
any other domain.

**Authentication** is local password auth. OIDC is a single-file change, as
described above, but it is not wired to a provider out of the box.

---

## Licence

The reference implementation in this directory is licensed under the
**Apache License 2.0**. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

The governance framework it implements, meaning the specification, architecture
and methodology documents in the parent directory, is released separately under
**CC BY 4.0**. See the [repository root](../README.md) and
[DISCLAIMER](../disclaimer.md).

The two are licensed differently on purpose: CC BY 4.0 suits the documents, and
Creative Commons advises against applying its licences to software.
