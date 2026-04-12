# System Invariants Catalogue

**Version:** 2.0-template | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](./codified-rules.md) §16-18
**Purpose:** Complete catalogue of system invariants with enforcement layer, validation method, and implementation guidance. Invariants are hard rules that the system must never violate regardless of user role, workflow state, or API path.

> **Design principle:** Schema constraints handle data integrity. Service-layer gates handle business logic. Neither layer operates without the other. Every invariant below identifies which layer enforces it, so implementation teams know where the constraint must live.

---

## How to Read This Catalogue

| Column | Meaning |
|---|---|
| **ID** | Unique invariant identifier. RINV = Risk, CINV = Control, PINV = Policy, TINV = Threat Modeling. |
| **Rule** | The constraint expressed as a natural-language rule. |
| **Enforcement Layer** | Where the constraint is implemented: Schema (DB constraint), Service (API/business logic), or Both. |
| **Enforcement Mechanism** | The specific technical mechanism that prevents violation. |
| **Violation Behaviour** | What happens when something attempts to violate the invariant. |
| **Spec Reference** | Cross-reference to the Codified Rules Specification section. |

---

## Risk Management Invariants (RINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| RINV-1 | Residual risk NEVER updated without validated evidence | Service | Residual score fields carry a `locked` flag. API validation gate checks all 5 conditions before releasing the lock. Direct DB writes blocked by trigger or RLS policy. | Write rejected; residual remains at inherent score | §4.7 |
| RINV-2 | Risk appetite NEVER downgraded without formal governance | Service | Appetite threshold changes require governance approval workflow. No API endpoint permits direct appetite modification. | Change request rejected; logged as unauthorised modification attempt | §1.2 |
| RINV-3 | Control owners NEVER assigned as risk owners | Schema + Service | FK constraint check on `risk_owner_id` against `control_owner_id` for linked controls. Service layer validates on assignment. | Assignment rejected; validation error returned | §2.2 (SEP-3) |
| RINV-4 | Acceptance NEVER permanent — always time-bound | Schema | `NOT NULL` constraint on `acceptance_expiry` when `treatment_decision = Accept`. | DB write rejected; constraint violation | §5.5 |
| RINV-5 | Critical risks NEVER accepted | Service + Schema | Service layer rejects `treatment_decision = Accept` when `inherent_rating = Critical`. CHECK constraint as backup. | Decision rejected; must select Mitigate, Transfer, or Avoid | §5.5 |
| RINV-6 | Risk readout NEVER skipped for risks rated Moderate or above | Service | Phase gate check at Phase 5 transition. Risks rated Moderate, High, or Critical cannot advance past Phase 5 without readout confirmation. | Phase transition blocked | §7.4 |
| RINV-7 | Issues NEVER scored as risks without promotion criteria met | Service | Intake triage gate validates promotion criteria before creating a risk record from an issue. | Risk record creation blocked; item remains in Issue Management | §3.6 |
| RINV-8 | Scoring NEVER begins without preconditions satisfied | Service | Phase 2 gate enforces 4-item precondition checklist. All items must be TRUE before scoring fields become editable. | Phase transition blocked; scoring fields remain read-only | §4.1 |
| RINV-9 | Planned/partial/unvalidated controls NEVER reduce residual risk | Service | Scoring engine filters linked controls. Only controls with `lifecycle_status = Operating` and `ce_rating ≠ CE-Unvalidated` contribute to likelihood adjustment. | Planned controls excluded from calculation automatically | §4.6 |
| RINV-10 | Every risk MUST have Risk Owner AND Risk Stakeholder | Schema | `NOT NULL` constraint on `risk_owner_id` and `risk_stakeholder_id` in risks table. | DB write rejected; constraint violation | §2.1 |
| RINV-11 | Expired risks ALWAYS escalated — no silent expiry | Service | Scheduled job checks `acceptance_expiry` daily. Expired acceptances trigger automatic escalation workflow and flag risk as Above Appetite. | Auto-escalation to Risk Owner → Risk Stakeholder → CISO | §5.5, §6.1 |
| RINV-12 | Treatments NEVER presented at readout without GRC Engineer validation + treatment owner commitment | Service | Phase 4 gate checks `grc_eng_validated = TRUE` and `owner_committed = TRUE` on all linked treatment records. | Phase transition blocked; treatment records flagged as incomplete | §5.2 |
| RINV-13 | Partial treatment selection ALWAYS documented with rationale | Service | API validation requires `partial_treatment_rationale` field when fewer than all proposed treatments are selected. | Save rejected; rationale field required | §5.2 |

---

## Control Management Invariants (CINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| CINV-1 | CE evidence REQUIRED for any rating other than CE-Unvalidated | Service | API validation requires `ce_evidence_ref` to be non-empty when `ce_rating ≠ CE-Unvalidated`. | CE rating save rejected; evidence field required | §4.5 |
| CINV-2 | Design/Implementation controls NEVER used as CE evidence in risk scoring | Service | Scoring engine filters linked controls by `lifecycle_status`. Only `Operating` status controls contribute CE to risk calculations. | Controls silently excluded from scoring; no error (by design) | §9.1 (OL rules) |
| CINV-3 | Control Owner NEVER assigned as Risk Owner for linked risks | Schema + Service | Same as RINV-3. Bidirectional check: also prevents risk owner assignment to someone who is control owner on a linked control. | Assignment rejected | §2.2 (SEP-3) |
| CINV-4 | CE assessment NEVER performed on Decommissioned deployments | Service | API rejects CE rating updates when `deployment_status = Decommissioned`. UI hides CE fields. | Write rejected; deployment is read-only | §9.3 (DL-3) |
| CINV-5 | Failure state ALWAYS propagates warning to linked risk records | Service | Control status change trigger: when any control_objective transitions to `Failure`, all linked risk records receive a warning flag and `residual_score_locked = TRUE`. | Automatic cascade; no manual action required | §9.1 (OL-5) |
| CINV-6 | Worst-case CE across deployments ALWAYS used in scoring | Service | Scoring engine queries all deployments for a linked control and selects `MIN(ce_rating)`. Never averages, never uses best-case. | Automatic; scoring engine logic | §4.6 |
| CINV-7 | Test history records are IMMUTABLE | Schema | Test result records have no UPDATE or DELETE permissions. Corrections create new superseding records with reference to the original. | UPDATE/DELETE rejected at DB layer | §10.1 (TST-1) |
| CINV-8 | Control retirement BLOCKED if linked risks are above-appetite and unmitigated | Service | Deprecation workflow checks all linked risk records. If any have `status = Above_Appetite` and `treatment_decision ≠ {Accepted, Transferred, Closed}`, transition is blocked. | Lifecycle transition rejected | §9.1 (OL-3) |
| CINV-9 | Asset decommission NEVER silently removes risk-control linkages | Service | Asset decommission workflow flags all linked control_deployments for review. Risk Analyst notified. Linkages preserved in read-only state until explicitly reviewed and re-mapped or closed. | Decommission proceeds but linkages remain visible; risk re-assessment required | §8.1 (CH-6) |
| CINV-10 | CE expiry auto-downgrades to CE-Unvalidated; no manual override | Service | Scheduled job checks `ce_last_assessed` against expiry thresholds per control frequency. Expired CE automatically set to `CE-Unvalidated`. No API endpoint permits manual override of expired CE. | Automatic downgrade; Risk Analyst notified | §10.2 |

---

## Policy Management Invariants (PINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| PINV-1 | Every Active policy MUST have ≥1 linked control_objective | Service | Policy activation gate checks `linked_controls.count ≥ 1`. Policies with zero linked controls cannot transition to Active. | Lifecycle transition blocked; governance gap flagged | §12.1 (PH-1) |
| PINV-2 | Policy exceptions NEVER permanent — always time-bound | Schema | `NOT NULL` constraint on `expiry_date` in policy_exceptions table. | DB write rejected; constraint violation | §12.3 (PE-1) |
| PINV-3 | Policy deprecation NEVER silently removes risk-policy linkages | Service | Deprecation workflow preserves all risk-policy linkages. Linked control_objectives flagged for re-mapping within 60 days. Risk records notified. | Deprecation proceeds but linkages remain; re-mapping SLA starts | §14.1 (PC-2) |
| PINV-4 | Compliance-mapped policies MUST have Annual review cycle | Schema + Service | Policies with non-empty `compliance_mappings` that include annual-audit frameworks have `review_cycle` constrained to `Annual`. Service validates on save. | Save rejected if Biennial selected for compliance-mapped policy | §15 (CF-4) |
| PINV-5 | Policy approval REQUIRES CISO or above — no self-approval | Service | Approval workflow validates `policy_approver_id ≠ policy_owner_id` and `approver.role_level ≥ CISO`. | Approval rejected; must be approved by CISO or delegate | §13.1 (PL-1) |
| PINV-6 | Under Revision policies remain enforceable | Service | Policy revision creates a draft version. Prior Active version remains the system-of-record until new version reaches Active status. No gap in enforcement. | No violation possible; architecture prevents gap by design | §13.1 (PL-3) |
| PINV-7 | Standard revision ALWAYS triggers control alignment check | Service | Standard version change triggers notification to all linked Control_Activity owners. Alignment confirmation required within 30 days. Unconfirmed alignments flagged as governance gaps. | Automatic notification; SLA tracking begins | §14.1 (PC-1) |
| PINV-8 | Policy retirement BLOCKED if linked risks are Critical/High and unmitigated | Service | Deprecation workflow checks linked risk ratings. If any linked risk is `Critical` or `High` with `treatment_decision ≠ {Mitigated, Transferred, Closed}`, transition blocked. | Lifecycle transition rejected | §13.1 (PL-2) |
| PINV-9 | Version history is IMMUTABLE — always retained for audit | Schema | PolicyVersion records have no UPDATE or DELETE permissions. All changes create new version records. | UPDATE/DELETE rejected at DB layer | §12.2 |

---

## Threat Management Invariants (TINV)

| ID | Rule | Enforcement Layer | Enforcement Mechanism | Violation Behaviour | Spec Ref |
|---|---|---|---|---|---|
| TINV-1 | Threat Scenario MUST have mitigation OR local acceptance (Low) OR risk promotion (Medium+) | Service | Phase validation gate enforces that all scenarios must resolve to an allowed end-state before a threat model can be signed off. | Phase transition from Review to Active blocked | §19.3 |
| TINV-2 | Threat Model CANNOT proceed from Review to Active without AppSec and System_Owner sign-off | Service | Review gate requires both user identities to explicitly log a signature. | Phase transition blocked until both signatures present | §19.3 |
| TINV-3 | Medium, High, or Critical threat scenarios CANNOT be locally "Accepted" | Service | Rejects any `status = Accepted` change event if `inherent_severity >= Medium`, unless the promotion flag and `promoted_risk_id` are supplied simultaneously. | API returns HTTP 400; promotion required | §19.3 |
| TINV-4 | Full Mitigation of a threat scenario REQUIRES an active, linked control_deployment | Schema + Service | The `threat_mitigation_links` schema relies on FKs to `controls` table. The service layer verifies the control is active. | Cannot flag scenario as `status = Mitigated` | §19.3 |

---

## Implementation Guidance

### Enforcement Priority

When implementing invariants, prioritise in this order:

1. **Schema constraints first.** `NOT NULL`, `CHECK`, FK constraints, and immutability (revoked UPDATE/DELETE) are the strongest enforcement because they cannot be bypassed by any application code path, API, or direct database access.

2. **Service-layer gates second.** Multi-condition business logic that cannot be expressed as simple column constraints. These are the phase gates, scoring engine filters, and workflow validations.

3. **Scheduled jobs third.** Time-based invariants (CE expiry, acceptance expiry, SLA breach detection) that require periodic evaluation rather than per-transaction enforcement.

### Testing Invariants

Every invariant should have at least two test cases:

- **Positive test:** Confirm the system allows valid operations that comply with the invariant.
- **Negative test:** Confirm the system rejects operations that would violate the invariant and produces the correct error/behaviour.

For schema-layer invariants, test both through the API and via direct SQL to confirm the constraint exists at the database level.

### Adding New Invariants

When adding invariants to this catalogue:

1. Assign the next sequential ID in the appropriate domain (RINV, CINV, PINV, TINV)
2. Identify the enforcement layer (Schema, Service, or Both)
3. Define the specific mechanism (constraint type, gate check, trigger)
4. Define the violation behaviour (what the user sees or what the system does)
5. Cross-reference to the Codified Rules Specification section
6. Write positive and negative test cases before implementation

---

*This catalogue is released under CC BY 4.0. Adapt freely with attribution.*
