# Configuring the platform for your organisation

Everything the specification marks `[CUSTOMISE]` lives in
[`config/governance.yml`](../config/governance.yml). Aligning the tool to your
operating model is a file edit and a restart, not a fork.

```bash
$EDITOR config/governance.yml
docker compose restart api
```

The file is bind-mounted, not baked into the image, so there is nothing to
rebuild. To keep your configuration outside the checkout entirely, point
`GOVERNANCE_CONFIG_FILE` in `.env` at a path of your own.

---

## What you can change

Every row below is a `[CUSTOMISE]` block in the specification. The
**Specification** column names the section of
[`codified-rules.md`](../../specification/codified-rules.md) that defines what
the setting means, so you can read the rule before you change the number.

| Section | Governs | Specification |
|---|---|---|
| `organisation` | Name and tagline shown throughout the UI | None |
| `scoring.rating_bands` | Where each appetite band starts and stops | codified-rules §1.2 |
| `scoring.review_cadence_days` | Re-evaluation cadence per rating | §5.4 |
| `acceptance` | Which ratings may be accepted, for how long, by whom | §5.5 |
| `control_effectiveness.likelihood_reduction` | What each CE rating buys in likelihood | §4.6 |
| `control_effectiveness.expiry_months` | How long CE evidence stays valid | §10.2 |
| `control_effectiveness.degradation_sla_days` | Response window when a control degrades | §11.2 |
| `risk.tiers` | Your tier model and its scope boundaries | §3.7 |
| `risk.intake_sources` | Authoritative routes into the register | §3.2 |
| `controls.families` | Your control framework's taxonomy | §8.3 |
| `controls.types`, `test_frequencies`, `asset_tiers` | Control and asset vocabulary | §8.2 |
| `policy.types`, `review_cycles` | Policy taxonomy | §12 |
| `policy.compliance_frameworks` | Frameworks selectable as mappings | §15 |
| `policy.annual_audit_frameworks` | Which mappings force an Annual cycle | §15 (CF-4) |
| `policy.exceptions` | Exception windows and review triggers | §12.3 |
| `threat.*` | Local acceptance window and promotion threshold | §19.3 |
| `roles.definitions` | Your roles and their seniority ordering | §2.1 |
| `roles.ownership_by_severity` | Minimum seniority to own a risk at each rating | §2.3 |
| `escalation.*` | Escalation and re-alignment windows | §6, §14 |
| `treatment.*` | Effort bands and check-in cadence | §5.2 |

## What you cannot change, and why

Lifecycle state names, the 1-5 impact and likelihood scales, control
effectiveness rating names, treatment strategies and the five rating band names
are fixed.

The invariants and the database constraints reference them by name. RINV-5 says
a Critical risk cannot be accepted, and `ck_risks_critical_never_accepted` is a
`CHECK` constraint that enforces exactly that at the database layer. Renaming
`Critical` at runtime would leave the constraint pointing at a band that no
longer exists, and the enforcement would quietly stop working.

Band *boundaries* are fully configurable. If your appetite says anything at 16 or
above is Critical, move the boundary; the name stays.

---

## Worked example: a tighter appetite

Suppose your risk appetite is stricter than the shipped baseline. You want
Critical to start at 16 rather than 20, and you do not permit acceptance of High
risks at all.

```yaml
scoring:
  rating_bands:
    - { rating: Critical,     min: 16, max: 25, appetite: Above Appetite }
    - { rating: High,         min: 12, max: 15, appetite: Above Appetite }
    - { rating: Moderate,     min: 10, max: 11, appetite: Above Appetite }
    - { rating: Moderate-Low, min: 5,  max: 9,  appetite: At Appetite }
    - { rating: Low,          min: 1,  max: 4,  appetite: Within Appetite }

acceptance:
  Critical:     { acceptable: false, max_days: 0, approver: null }
  High:         { acceptable: false, max_days: 0, approver: null }   # tightened
  Moderate:     { acceptable: true,  max_days: 180, approver: VP }
  Moderate-Low: { acceptable: true,  max_days: 360, approver: Director }
  Low:          { acceptable: true,  max_days: 365, approver: Risk_Owner }
```

After `docker compose restart api`, RINV-5 refuses acceptance at High as well as
Critical. No code changed, and the invariant catalogue at `/api/engine/invariants`
reports the same rule with the new behaviour.

### Existing risks are not silently re-rated

A stored rating is a snapshot of the assessment that produced it (OUT-5). Moving
your bands does not retroactively re-rate risks that were already scored, for the
same reason a control effectiveness change does not silently rescore a residual:
the register would change underneath the people accountable for it.

Instead the platform surfaces the divergence. A risk whose stored rating differs
from what its score would rate today carries a `rating_drift` flag naming both,
so the analyst re-assesses deliberately. New assessments use the new bands
immediately.

---

## Worked example: your own control framework

Replace the taxonomy wholesale. Nothing else depends on these names.

```yaml
controls:
  families:
    - CC    # Common Criteria
    - AC    # Access Control
    - CM    # Change Management
    - SC    # System Communications
```

Control families are validated at the service layer rather than by a `CHECK`
constraint, precisely so this is a config change and not a schema migration.
A create or update naming a family you have not configured is refused with a
message that names the file to add it to.

---

## Worked example: adding a role

```yaml
roles:
  definitions:
    # ... existing roles ...
    - { id: Data_Protection_Officer, level: 4, description: Statutory DPO }
```

The role becomes assignable immediately. To make it *meaningful*, so that it can
fire a particular lifecycle transition, name it in that transition's `roles`
tuple in the relevant `machine.py`. That part is deliberately code: which roles may fire
which gates is part of your separation-of-duties design, and it belongs where it
can be reviewed alongside the gate it guards.

Two constraints the loader enforces:

- `Admin` and `CISO` must exist. The platform's own authorisation depends on them.
- `CISO` must hold the highest level of any non-Admin role, because PINV-5
  requires policy approval at CISO or above.

---

## Validation

The configuration is validated strictly at boot. A misconfigured appetite model
is a governance defect, not a runtime inconvenience, so the API refuses to start
rather than scoring risks against a broken model.

It will refuse to start if, among other things:

- your rating bands leave a score between 1 and 25 unrated, or assign one to two
  bands
- a band is marked acceptable but given a zero-day window
- `CE-Unvalidated` is configured to buy a likelihood reduction (RINV-9)
- a likelihood reduction exceeds what a 1-5 scale can express
- a test frequency has no CE expiry window
- `annual_audit_frameworks` names a framework absent from `compliance_frameworks`
- `ownership_by_severity` names a seniority absent from the ladder
- `CISO` is missing or ranked below another role

Each failure names the exact key and explains what is wrong.

```bash
docker compose exec api python config_test.py
```

That suite proves both halves: that invalid models are refused, and that valid
changes actually take effect.

---

## Where configuration ends and code begins

| Change | How |
|---|---|
| Appetite thresholds, SLAs, windows | `config/governance.yml` |
| Taxonomy: families, tiers, sources, frameworks, roles | `config/governance.yml` |
| Which roles may fire which transition | `modules/<domain>/machine.py` |
| A new precondition on an existing gate | `modules/<domain>/machine.py` |
| A new invariant | `modules/<domain>/invariants.py` |
| A new cascade | `modules/cascades.py` |
| A new domain module | `models · machine · invariants · service · router` |

The dividing line is deliberate. Thresholds and taxonomy are one organisation's
expression of the framework, so they are data. Which rule guards which gate is
the framework itself, so it is code that can be reviewed, diffed and tested.

That has a consequence worth stating plainly: the rows below the first two are
not configuration changes but framework changes wearing different clothes. A new
invariant needs a row in
[`invariants-catalogue.md`](../../specification/invariants-catalogue.md) and a
`spec_ref` pointing at a real section of
[`codified-rules.md`](../../specification/codified-rules.md), or
`tools/check_invariant_drift.py` and `tools/check_spec_references.py` fail the
build. [CONTRIBUTING.md](../../CONTRIBUTING.md) sets out the route.
