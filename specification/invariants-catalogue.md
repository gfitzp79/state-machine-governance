# System Invariants Catalogue

**Version:** 2.2-template | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](./codified-rules.md) §16-24
**Purpose:** Complete catalogue of system invariants with enforcement layer, validation method, and implementation guidance. Invariants are hard rules that the system must never violate regardless of user role, workflow state, or API path.

> **Design principle:** Schema constraints handle data integrity. Service-layer gates handle business logic. Neither layer operates without the other. Every invariant below identifies which layer enforces it, so implementation teams know where the constraint must live.

> **`Cascade` is a fourth layer, not a euphemism.** A handful of rules are not
conditions an entity must satisfy but things that must *happen* when something
else changes. They cannot be written as a predicate without duplicating the
invariant they exist to maintain, and they run inside the originating
transaction, so a cascade that would violate an invariant rolls the whole
operation back. Where a rule is marked `Cascade`, the condition it maintains is
enforced by a named invariant alongside it: AINV-5 keeps AINV-2 true.

> **Enforcement claims are load-bearing.** An invariant that says `Schema` must have a genuine `CHECK` constraint, `NOT NULL`, foreign key, or trigger behind it. `Both` requires both layers independently. An overstated enforcement claim is worse than an understated one, because it tells an assessor that a bypass is impossible when it is merely inconvenient. The layer recorded here is the layer the [reference implementation](../platform) actually uses.

---

## How to Read This Catalogue

| Column | Meaning |
|---|---|
| **ID** | Unique invariant identifier. RINV = Risk, CINV = Control, PINV = Policy, TINV = Threat Modelling, AINV = Assurance and Compliance. A few rules keep the identifier they carry in the specification body — `SEP-1` (§2.2), `PE-5` (§12.3), `TM-PARTIAL` (§19.3) — because renaming them would break the cross-reference that makes them findable. |
| **Rule** | The constraint expressed as a natural-language rule. |
| **Enforcement Layer** | Where the constraint is implemented: Schema (DB constraint or trigger), Service (API/business logic), Both, or Cascade. |
| **Enforcement Mechanism** | The specific technical mechanism that prevents violation. |
| **Violation Behaviour** | What happens when something attempts to violate the invariant. |
| **Spec Reference** | Cross-reference to the Codified Rules Specification section. |

**Counts.** 57 invariants: 14 risk, 12 control, 10 policy, 12 threat, 9 compliance.

---

## Risk Management Invariants (RINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| RINV-1 | Residual risk is never updated without validated evidence | Both | `residual_score_locked` flag released only by `GATE_RESIDUAL_VALIDATED`; while locked, residual may not diverge from inherent | Write rejected; residual remains at the inherent score | [scoring-model §7](./scoring-model.md) |
| RINV-2 | Risk appetite is never downgraded without formal governance | Service | No API endpoint writes appetite thresholds; they are engine configuration, changed only by redeploying the operating model | Change request rejected; logged as an unauthorised modification attempt | §1.2 |
| RINV-3 | Control owners are never assigned as risk owners for linked risks | Service | Risk owner checked against `control_owner_id` on every linked objective, both on assignment and at link time | Assignment rejected; validation error returned | §2.2 (SEP-3) |
| RINV-4 | Acceptance is never permanent; it is always time-bound and within the rating limit | Both | `CHECK` constraint requires an expiry date; service caps the window per rating | Write rejected; constraint violation | §5.5 |
| RINV-5 | Critical risks are never accepted | Both | `CHECK` constraint plus service-layer rejection of Accept on a Critical rating | Decision rejected; must select Mitigate, Transfer or Avoid | §5.5 |
| RINV-6 | Risk readout is never skipped for risks rated Moderate or above | Service | Phase 5 gate requires `readout_confirmed` for Moderate, High and Critical | Phase transition blocked | §7.4 |
| RINV-7 | Issues are never scored as risks without promotion criteria met | Service | Promoted items must carry triage confirmation before leaving Preconditions | Risk record creation blocked; item remains in issue management | §3.6 |
| RINV-8 | Scoring never begins without preconditions satisfied | Service | Scoring fields remain unwritable until the 4-item Phase 2 checklist passes | Phase transition blocked; scoring fields stay read-only | §4.1 |
| RINV-9 | Planned, partial or unvalidated controls never reduce residual risk | Service | Scoring engine filters to Operating objectives with live deployments and non-expired evidence, then caps the likelihood reduction at the resolved CE | Residual likelihood reduction beyond the CE ceiling is rejected | §4.6 |
| RINV-10 | Every risk has both a Risk Owner and a Risk Stakeholder | Both | Service enforcement from Phase 3 onward; `CHECK` constraint enforces SEP-1 | Write rejected; constraint violation | §2.1 |
| **SEP-1** | The Risk Owner is never also the Risk Stakeholder | Both | `CHECK` constraint on the risks table plus service validation | Assignment rejected | §2.2 |
| RINV-11 | Expired acceptances are always escalated; no silent expiry | Service | Daily scheduled job flags expired acceptances; an unflagged one is invalid | Auto-escalation to Risk Owner, then Risk Stakeholder, then CISO | §5.5, §6.1 |
| RINV-12 | Treatments are never presented at readout without GRC Engineer validation and treatment owner commitment | Service | Phase 4 gate checks both flags on every linked treatment record | Phase transition blocked; treatment records flagged incomplete | §5.2 |
| RINV-13 | Partial treatment selection is always documented with a rationale | Service | Rationale required when fewer treatments are selected than proposed | Save rejected; rationale field required | §5.2 |

> **On RINV-3.** This is deliberately `Service`, not `Both`. The separation it enforces is relational — it depends on which controls are linked to the risk at the moment of assignment — and a `CHECK` constraint cannot see across tables. Enforcing it means checking on *both* sides: RINV-3 when the risk owner is set, CINV-3 when the control owner is set. Either one alone is defeated by performing the two assignments in the other order.

> **On RINV-2.** Appetite thresholds are configuration, not data. There is no endpoint that writes them because there is no table that holds them. Changing appetite means changing the operating model and redeploying it, which leaves a reviewable diff — the formal governance the rule asks for.

---

## Control Management Invariants (CINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| CINV-1 | Control effectiveness evidence is required for any rating other than CE-Unvalidated | Both | `CHECK` constraint on `control_deployments` plus service validation | CE rating save rejected; evidence reference required | §4.5 |
| CINV-2 | Design and Implementation controls are never used as CE evidence in risk scoring | Service | Scoring engine filters to Operating objectives; others resolve to CE-Unvalidated | Controls silently excluded from scoring, with the exclusion reason surfaced | §9.1 (OL rules) |
| CINV-3 | A Control Owner is never assigned as Risk Owner for a linked risk | Service | Control owner checked against the risk owner of every linked risk. The risk-side half is RINV-3; both directions are needed or the rule is defeated by ordering the two assignments the other way round | Assignment rejected | §2.2 (SEP-3) |
| CINV-4 | Control effectiveness is never assessed on a decommissioned deployment | Service | Decommissioned deployments are read-only; CE writes are rejected | Write rejected; the deployment is frozen | §9.3 (DL-3) |
| CINV-5 | A Failure state always propagates a warning to every linked risk record | Service | `control.failed` cascade flags linked risks and sets `residual_score_locked` | Automatic cascade; no manual action required | §9.1 (OL-5) |
| CINV-6 | Worst-case control effectiveness across deployments is always used in scoring | Service | Scoring engine takes the minimum CE across qualifying deployments | Automatic; the engine never averages and never takes best case | §4.6 |
| CINV-7 | Test history records are immutable | Schema | Database trigger rejects `UPDATE` and `DELETE` on `control_tests` | `UPDATE` and `DELETE` rejected at the database layer; corrections supersede | §10.1 (TST-1) |
| CINV-8 | Control retirement is blocked if linked risks are above appetite and unmitigated | Service | Deprecation gate walks every linked risk before permitting the transition | Lifecycle transition rejected | §9.1 (OL-3) |
| CINV-9 | Asset decommission never silently removes risk-control linkages | Service | Decommission preserves linkages read-only and notifies the Risk Analyst | Decommission proceeds; linkages remain visible and re-assessment is required | §8.1 (CH-6) |
| CINV-10 | Expired control effectiveness auto-downgrades to CE-Unvalidated with no override | Service | Scheduled job downgrades on expiry; no endpoint permits a manual override | Automatic downgrade; Risk Analyst notified | §10.2 |
| CINV-11 | Control effectiveness never exceeds the ceiling its automation level supports | Service | CE compared against `controls.automation_ce_ceiling` for the parent objective's automation level. A manual control cannot hold the top rating however good its last test | CE rating rejected; raise the automation level or lower the claim | §24.1 |
| CINV-12 | A key control never evidences a requirement on assurance weaker than the configured floor | Service | Assurance methods are ordered weakest first; a key control must sit at or above `controls.key_control_minimum_assurance` | Link rejected; strengthen the assurance method or unmark the key control | §24.2 |

> **On CINV-11.** Without a ceiling, a spreadsheet reviewed quarterly can claim
the same effectiveness as an enforced platform policy, and buy the same
likelihood reduction under RINV-9. A manual control's evidence describes the last
time a person performed it, which says nothing about the occasion nobody does.
That occasion is what the control exists for.

> **CE lives on the deployment.** CINV-1, CINV-4 and CINV-10 all attach to `control_deployments` rather than to the control objective, because a control is only as effective as the place it actually runs. CINV-6 then resolves the objective's CE as the *worst* case across its deployments. See §8.1 for the three-level hierarchy and [data-model.md](../architecture/data-model.md) for the tables.

---

## Policy Management Invariants (PINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| PINV-1 | Every Active policy has at least one linked control objective | Service | Activation gate counts linked controls; zero blocks the transition | Lifecycle transition blocked; governance gap flagged | §12.1 (PH-1) |
| PINV-2 | Policy exceptions are never permanent; they are always time-bound | Schema | `NOT NULL` constraint on `policy_exceptions.expiry_date` | Write rejected; constraint violation | §12.3 (PE-1) |
| PINV-3 | Policy deprecation never silently removes risk-policy linkages | Service | Deprecation cascade preserves linkages and starts a 60-day re-mapping SLA | Deprecation proceeds; linkages remain and the re-mapping clock starts | §14.1 (PC-2) |
| PINV-4 | Compliance-mapped policies carry an Annual review cycle | Service | Service validates the cycle against the mapped frameworks on save | Save rejected if Biennial is selected for a compliance-mapped policy | §15 (CF-4) |
| PINV-5 | Policy approval requires CISO or above, and never self-approval | Both | `CHECK` constraint blocks owner == approver; service checks the role level | Approval rejected; must be approved by CISO or a delegate | §13.1 (PL-1) |
| PINV-6 | Policies Under Revision remain enforceable | Service | A revision captures an immutable version and drafts forward; the Active version stays system of record until the new one reaches Active | No violation possible; the architecture prevents an enforcement gap | §13.1 (PL-3) |
| PINV-7 | Standard revision always triggers a control alignment check | Service | Revision cascade notifies linked control owners with a 30-day SLA | Automatic notification; SLA tracking begins | §14.1 (PC-1) |
| PINV-8 | Policy retirement is blocked if linked risks are Critical or High and unmitigated | Service | Deprecation gate walks every linked risk before permitting the transition | Lifecycle transition rejected | §13.1 (PL-2) |
| PINV-9 | Version history is immutable and always retained for audit | Schema | Database trigger rejects `UPDATE` and `DELETE` on `policy_versions` | `UPDATE` and `DELETE` rejected at the database layer | §12.2 |
| **PE-5** | An approved exception past its expiry date is a governance gap, not a valid state | Service | Scheduled job expires overdue exceptions and notifies the CISO | Governance gap flagged; CISO notified | [state-transitions §6](./state-transitions.md) |

> **On PINV-4.** This is `Service`, not `Both`. Which frameworks demand an annual cycle is configuration, and a `CHECK` constraint cannot read a configuration file. The check belongs where the framework list lives.

> **On PE-5.** An exception does not expire because a job ran. It expires because the date passed. The job's purpose is to make the *record* agree with reality — which is why PE-5 is written as a statement about valid states rather than as a description of the job. A system where an expired exception silently remains Approved has not merely failed to notify; it is asserting something untrue.

---

## Threat Management Invariants (TINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| TINV-1 | Every threat scenario reaches a permitted end state: mitigated, locally accepted below the promotion threshold, or carried by the risk register | Service | Review → Active gate blocks while any scenario is still unresolved | Phase transition from Review to Active blocked | §19.3 |
| TINV-2 | A threat model cannot be Active without independent AppSec and System Owner sign-off | Both | `CHECK` constraint blocks AppSec sign-off by the system owner; the Review gate requires both signatures present | Phase transition blocked until both signatures are present | §19.3 |
| TINV-3 | Medium, High and Critical threat scenarios are never locally accepted | Both | `CHECK` constraint plus service rejection; promotion is the only other path | Rejected; promotion to the risk register required | §19.3 |
| TINV-4 | Full mitigation of a threat scenario requires an active, linked control deployment | Both | FK from `threat_mitigation_links` to **`control_deployments`**, plus a service check that the deployment is Active or Degraded; a control failure re-opens the scenario | Cannot flag the scenario as Mitigated | §19.3 |
| TINV-5 | A locally accepted Low severity scenario carries an acceptance expiry no more than 12 months out | Both | `CHECK` constraint requires an expiry; service caps the window at 12 months | Rejected; expiry required and capped | §19.3 |
| TINV-6 | A promoted scenario always names the risk record it produced | Both | `CHECK` constraint requires `promoted_risk_id` when status is `Promoted_To_Risk` | Write rejected; promotion must create and link a risk record | §20.1, [data-model §8](../architecture/data-model.md) |
| **TM-PARTIAL** | A scenario is never Mitigated while any of its mitigation links asserts only partial coverage | Service | Status is derived from the whole link set, not the link being added. A partial link added to a mitigated scenario returns it to Identified | Status reverts to Identified; partial coverage is an open threat | §19.3 |
| TINV-7 | Environmental control posture is informative, never determinative: a scenario is never resolved by the ambient presence of a control | Service | The context engine is read-only and cannot write to a scenario. Mitigated requires an explicit `threat_mitigation_links` row asserted by a person. The threat-modelling analogue of LKH-3 | Mitigated status rejected when no mitigation link exists | §19.4 |
| TINV-8 | A scenario either promotes into a new risk or references existing ones, never both; the register never gains a duplicate exposure | Service | Exactly one configured risk link type may create a risk record. Linking to an existing risk is a reference, not a promotion | Link rejected; reference the existing risk instead of promoting again | §19.5 |
| TINV-9 | A component handling data at or above the sensitive threshold must declare the trust zone it sits in | Service | Component save validates `trust_zone` against the configured zones | Save rejected; declare where the component sits | §19.1 |
| TINV-10 | A scenario status change always carries a rationale or a linked artefact | Service | Accepted requires an acceptance rationale; Mitigated requires a link or a rationale. Evidence records are append-only at the database layer | Status change rejected without a reason | §19.5 |
| TINV-11 | An Active threat model has no sensitive component without at least one threat scenario | Service | Review → Active gate walks every component at or above the classification threshold | Sign-off blocked; the component was decomposed but never analysed | §19.4 |

> **TINV-4 links to a deployment, not a control.** This is the single most consequential modelling decision in the threat domain. A control objective is an intention; a deployment is the instance running on the asset the component sits on. Linking a scenario to an objective would let a scenario be "mitigated" by a control that exists everywhere except where the threat is. It also gives §20.2 something to fire on: a deployment that fails re-opens exactly the scenarios that depended on it.

> **TINV-7 is the load-bearing one.** Everything else in the threat domain would work without it, and the result would be a model that quietly stops finding threats as the environment matures. It is the reason the context engine has no write path at all, rather than a write path nobody currently calls. See §19.4 for the argument in full.

---

## Compliance and Assurance Invariants (AINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| AINV-1 | An excluded requirement always carries a documented justification | Both | `CHECK` constraint requires a rationale when the state is `Not_Applicable`, plus a gate precondition on the exclusion transition | Exclusion rejected; a Statement of Applicability must justify every omission | §22.2 |
| AINV-2 | A requirement is Covered only while a satisfying control is Operating and live where the requirement applies | Service | Gate and invariant share one predicate: a satisfying link, an Operating objective, and a live deployment inside the framework's scope. Re-checked on every write, so coverage cannot outlive the control that carried it | Covered rejected or revoked; the requirement returns to Gap | §23.1 |
| AINV-3 | Partial coverage is a gap, never coverage | Service | Satisfying levels are read from configuration, and status is derived from the whole link set. Downgrading the last Full link to Partial re-opens the requirement | Covered rejected; a requirement half-satisfied is not satisfied | §23.2 |
| AINV-4 | A compensating position is never permanent; it is always time-bound | Both | `CHECK` constraint requires an expiry; the gate caps the window and a scheduled job expires it | Rejected; set an expiry within the configured window | §23.3 |
| **AINV-5** | A failing or retired control revokes the compliance coverage that rested on it | Cascade | Cascade on `control.failed` and `control.deprecated` walks the coverage links and returns each affected requirement to Gap, unless another Operating control still satisfies it | Automatic; the position changes without anyone revisiting the register | §24.3 |
| AINV-6 | A framework whose content may not be redistributed never carries requirement text in this repository | Service | The catalogue loader refuses at boot. Licensed content is imported into the database by the operator, never into the tree | Boot refused; the licence is enforced rather than documented | §21.2 |
| AINV-7 | A framework version is immutable once its requirements are loaded | Service | Version changes rejected while requirements exist. A new version is a new record, because renumbering between versions would silently re-point existing coverage assertions | Version change rejected; create the new version as its own framework | §21.3 |
| AINV-8 | Only an adopted framework carries an assessed position | Service | Gate blocks assessment on an unadopted framework | Assessment rejected; adopt the framework first | §21.4 |
| AINV-9 | No requirement of an adopted framework is Covered while no asset declares itself in that framework's scope | Service | With no scope declared, AINV-2 accepts a live deployment anywhere. This refuses the undeclared case explicitly, so a percentage is never reported against an estate nobody assessed | Covered rejected; declare the assets the framework applies to | §23.1 |
| AINV-10 | A coverage assertion always uses a configured coverage level | Service | Level validated against `compliance.coverage_levels` on write | Link rejected; an unconfigured level would silently fail to count | §23.2 |

> **AINV-5 is marked `Cascade` rather than `Service`.** It is a rule about what
must *happen* when a control fails, not a condition an entity must satisfy.
Writing it as a predicate would mean asserting the post-cascade state on every
write, which is precisely what AINV-2 already does. The two are a pair: AINV-5
performs the revocation, AINV-2 refuses to let a Covered position survive
without it.

> **AINV-6 is the unusual one.** It makes a licence obligation enforceable. Every
other way of handling third-party framework content amounts to telling
contributors not to paste it in, which is a policy, not a control. Refusing to
boot is the control.

> **AINV-9 exists because of an arithmetic trap.** A coverage percentage over an
empty scope is not zero, it is undefined, and code that divides anyway reports
100%. An adopted framework nobody has scoped is the most dangerous state this
module can be in, because it produces a confident number about an estate that was
never assessed. The posture endpoint returns `null` rather than a percentage in
that case, and AINV-9 stops any requirement reaching Covered to begin with.

---

## Cross-Domain Enforcement

Some rules are not invariants on a single entity but properties of the system as
a whole. They are enforced by construction rather than by a predicate, which
means they have no row above — and are easy to lose sight of for that reason.

| Property | How it is guaranteed | Spec Ref |
|---|---|---|
| Every lifecycle change passes every applicable invariant | One write path: mutate → enforce → cascade → audit, in that order, in one transaction. No route bypasses it because no other route to the session exists | §16-18 |
| A cascade cannot leave the system in a state an invariant forbids | Cascades run inside the originating transaction, before the invariant sweep. A cascade that would violate an invariant rolls the whole operation back | §11.2, §20.2, §20.3 |
| Audit records cannot be revised | Append-only, enforced by database trigger — as for `control_tests` (CINV-7), `policy_versions` (PINV-9), and `threat_scenario_evidence` (TSE-1) | §7.3 |
| Separation of duties survives assignment ordering | Every separation rule is checked from both sides. See the note under RINV-3 | §2.2 |
| A compliance position never outlives the control beneath it | AINV-2 is re-evaluated on every write, and the §24.3 cascade revokes coverage the moment a control fails. Neither depends on anyone revisiting the register | §23.1, §24.3 |

---

## Implementation Guidance

### Enforcement Priority

When implementing invariants, prioritise in this order:

1. **Schema constraints first.** `NOT NULL`, `CHECK`, FK constraints, and immutability (trigger-rejected `UPDATE`/`DELETE`) are the strongest enforcement because they cannot be bypassed by any application code path, API, or direct database access.

2. **Service-layer gates second.** Multi-condition business logic that cannot be expressed as a column constraint: phase gates, scoring-engine filters, cross-table separation checks, and anything that reads configuration.

3. **Scheduled jobs third.** Time-based invariants (CE expiry, acceptance expiry, exception expiry, SLA breach detection) that require periodic evaluation rather than per-transaction enforcement.

A rule that can be enforced at a lower-numbered layer should be. Where a rule needs two layers, implement both rather than treating one as sufficient: the schema constraint holds against direct SQL, and the service check produces the message that tells a user what to do instead.

### Testing Invariants

Every invariant should have at least two test cases:

- **Positive test:** confirm the system allows valid operations that comply with the invariant.
- **Negative test:** confirm the system rejects operations that would violate it, and produces the correct error or behaviour.

For any invariant claiming `Schema` or `Both`, test through the API **and** via direct SQL. A test that only exercises the API cannot distinguish a genuine constraint from a service check wearing one's name — which is exactly the drift this column exists to prevent.

### Adding New Invariants

When adding invariants to this catalogue:

1. Assign the next sequential ID in the appropriate domain (RINV, CINV, PINV, TINV, AINV)
2. Identify the enforcement layer honestly — `Schema` only if a constraint or trigger genuinely exists
3. Define the specific mechanism (constraint type, gate check, trigger, job)
4. Define the violation behaviour (what the user sees, or what the system does)
5. Cross-reference to the Codified Rules Specification section, and **write that section if it does not yet exist**
6. Write positive and negative test cases before implementation

Step 5 is not bureaucracy. An invariant citing a section that was never authored is a rule with no stated reason, and a rule with no stated reason is the first one somebody removes.

---

*This catalogue is released under CC BY 4.0. Adapt freely with attribution.*
