# State Transitions Reference

**Version:** 2.2-template | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](./codified-rules.md) §4-§5 (Risk and Treatment), §9 (Controls), §13 (Policy), §19-§20 (Threat)
**Purpose:** Complete definition of every lifecycle state machine in the platform, including valid transitions, gate preconditions, blocking rules, and cascade behaviours. Designed for implementation teams to build phase-gate enforcement at the API layer.

> **Design principle:** Every state transition is gated. No phase can be entered until all preconditions are satisfied. Gates are enforced at the API layer, not in UI validation. UI elements may be hidden for convenience but the system does not depend on UI enforcement for correctness.

---

## Table of Contents

1. [Risk Lifecycle (7 Phases)](#1-risk-lifecycle-7-phases)
2. [Control Objective Lifecycle (6 States)](#2-control-objective-lifecycle-6-states)
3. [Control Activity Lifecycle (4 States)](#3-control-activity-lifecycle-4-states)
4. [Control Deployment Lifecycle (5 States)](#4-control-deployment-lifecycle-5-states)
5. [Policy Lifecycle (6 States)](#5-policy-lifecycle-6-states)
6. [Policy Exception Lifecycle (4 States)](#6-policy-exception-lifecycle-4-states)
7. [Threat Model Lifecycle (8 States)](#7-threat-model-lifecycle-8-states)
8. [Treatment Lifecycle (6 States)](#8-treatment-lifecycle-6-states)
9. [Requirement Assessment Lifecycle (6 States)](#9-requirement-assessment-lifecycle-6-states)
10. [Cross-Lifecycle Cascade Rules](#10-cross-lifecycle-cascade-rules)

---

## 1. Risk Lifecycle (7 Phases)

### State Machine Diagram

```
[1. Intake] → [2. Preconditions] → [3. Scoring] → [4. Treatment] → [5. Readout] → [6. Evidence+Residual] → [7. Monitoring]
     ↑                                                                                                            │
     └────────────────────────────────── RE-ASSESSMENT (triggered by control change, expiry, or drift) ───────────┘
```

### Phase Gate Definitions

#### Phase 1 → Phase 2: Intake to Preconditions

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_INTAKE_COMPLETE` |
| **Preconditions** | Structured risk statement complete (cause, threat_event, vulnerability, impact). All four fields non-empty. Impact references business impact, not technical failure only. |
| **Blocks if** | Risk statement incomplete or unstructured. Any of the four fields empty. |
| **On pass** | Risk record created. Risk_Owner assignment SLA begins (Critical: 3bd, all others: 5bd). |
| **Enforcement** | Service layer: API validates risk_statement JSON structure before allowing phase advance. |

#### Phase 2 → Phase 3: Preconditions to Scoring

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_PRECONDITIONS_MET` |
| **Preconditions** | All 4 items checked: (1) True risk confirmed per §3.6, (2) Risk tier assigned per §3.7, (3) All stakeholders identified (Risk_Owner, Risk_Analyst, Treatment_Owner, Control_Owner(s), Control_Operator(s)), (4) Control effectiveness assessed with evidence per §4.5. |
| **Blocks if** | Any precondition item unchecked. |
| **On pass** | Scoring fields (inherent_impact, inherent_likelihood) become editable. |
| **Enforcement** | Service layer: 4-item checklist API. All items must return TRUE. Enforces RINV-8. |

#### Phase 3 → Phase 4: Scoring to Treatment

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_SCORING_COMPLETE` |
| **Preconditions** | (1) Inherent impact scored (1-5), (2) Inherent likelihood scored (1-5), (3) Inherent score computed (impact × likelihood), (4) Inherent rating derived from score bands, (5) Risk_Owner assigned (NOT NULL), (6) Risk_Stakeholder assigned (NOT NULL). |
| **Blocks if** | Any scoring field empty. Risk_Owner or Risk_Stakeholder unassigned. Enforces RINV-10. |
| **On pass** | Treatment decision fields become editable. Treatment design workflow (§5.2) begins. |
| **Enforcement** | Schema: NOT NULL on risk_owner_id, risk_stakeholder_id. Service: field completeness check. |

#### Phase 4 → Phase 5: Treatment to Readout

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_TREATMENT_ALIGNED` |
| **Preconditions** | (1) At least one treatment linked to risk record, (2) GRC Engineer feasibility validation complete (`grc_eng_validated = TRUE`), (3) Treatment Owner commitment confirmed (`owner_committed = TRUE`), (4) Control framework mapping documented (if treatment_decision = Mitigate), (5) Control Owner and Operator acknowledgement (if new/modified control required). |
| **Blocks if** | No treatments linked. GRC Engineer validation incomplete. Treatment Owner not committed. Enforces RINV-12. |
| **On pass** | Risk enters readout queue for next governance forum. Risk_Owner notified. |
| **Enforcement** | Service layer: validates boolean flags on all linked risk_treatments records. |

#### Phase 5 → Phase 6: Readout to Evidence and Residual

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_READOUT_COMPLETE` |
| **Preconditions** | (1) Risk_Owner has reviewed and confirmed treatment plan at governance readout, (2) Readout date recorded, (3) For risks rated Moderate or above: readout is MANDATORY (cannot be bypassed). |
| **Blocks if** | Readout not completed for risks rated Moderate, High, or Critical. Enforces RINV-6. |
| **On pass** | Evidence collection phase begins. Residual scoring fields remain locked until Phase 6 gate passes. |
| **Enforcement** | Service layer: phase transition check. Risks with `inherent_rating ≥ Moderate` require `readout_confirmed = TRUE`. |

#### Phase 6 → Phase 7: Evidence and Residual to Monitoring

| Attribute | Value |
|---|---|
| **Gate name** | `GATE_RESIDUAL_VALIDATED` |
| **Preconditions** | All 5 conditions met: (1) Mitigations fully implemented, (2) Evidence provided (configs, logs, dashboards, audit artefacts), (3) Treatment effectiveness confirmed by Risk_Analyst, (4) Governance approval documented, (5) Risk drift tracked during treatment period. |
| **Blocks if** | Any of the 5 conditions unmet. Residual score fields remain read-only. Enforces RINV-1. |
| **On pass** | Residual score fields unlocked. Residual impact, likelihood, score, and rating become editable. Risk enters monitoring phase with SLA tracking active. |
| **Enforcement** | Service layer: 5-item validation gate. Schema: residual fields carry `locked` flag released only by gate function. |
| **Critical rule** | If treatment_decision = Accept: `acceptance_expiry` must be set (NOT NULL). If inherent_rating = Critical: Accept is blocked entirely. Enforces RINV-4 and RINV-5. |

#### Phase 7: Monitoring (Ongoing)

| Attribute | Value |
|---|---|
| **Active SLAs** | Re-evaluation cadence: Critical 14d, High 30d, Moderate 60d, Moderate-Low 90d. Acceptance expiry tracking. Treatment execution SLA tracking. |
| **Re-assessment triggers** | Control CE degradation on linked control. Acceptance expiry reached. Treatment SLA breach. External trigger (incident, regulatory change, threat intelligence). |
| **On re-assessment** | Risk returns to Phase 2 (Preconditions) or Phase 3 (Scoring) depending on the nature of the change. Full lifecycle re-traversal with updated data. |

---

## 2. Control Objective Lifecycle (6 States)

### State Machine Diagram

```
[Design] → [Implementation] → [Operating] ⇄ [Failure] ⇄ [Redesign]
                                    ↓
                              [Deprecated]
```

### Transition Rules

| From | To | Gate Preconditions | Blocking Rules |
|---|---|---|---|
| Design | Implementation | ≥1 Control_Activity defined AND deployment plan exists | None |
| Implementation | Operating | ≥1 deployment Active (OL-4) AND first CE assessed with evidence on a live deployment (CINV-1) | OL-4: blocked with zero active deployments |
| Operating | Failure | CE-Low on critical deployment OR test result = Fail on any deployment | None |
| Failure | Operating | Remediated without architectural change AND CE re-assessed upward | None |
| Failure | Redesign | Remediation requires architectural change to control design | None |
| Redesign | Implementation | Redesigned and ready for re-deployment | None |
| Operating | Deprecated | Governance-approved retirement | OL-3: BLOCKED if linked risks ≠ {Closed, Accepted, Transferred} |
| Any | Deprecated | With documented rationale + Risk_Owner notification for linked risks | OL-3 applies |

> **≥1, not all.** An earlier draft of this table required *all* target
> deployments Active while citing OL-4, which requires one. They cannot both be
> right, and requiring all of them is wrong: a control objective rolled out to
> eighty assets is operating on the day the first deployment goes live, and
> CINV-6 already handles the rest by resolving the objective's CE as the *worst*
> case across deployments. Requiring all would mean an objective is either fully
> deployed or not Operating at all, which describes no real rollout.

### Field Editability by State

| Field Group | Design | Implementation | Operating | Failure | Redesign | Deprecated |
|---|---|---|---|---|---|---|
| CE fields (rating, evidence, assessed_by) | Read-only | Read-only | **Editable** | Read-only | Read-only | Read-only |
| Test scheduling | Inactive | Inactive | **Active** | Inactive | Inactive | Inactive |
| Activity linkage | Editable | Editable | Editable | Read-only | Editable | Read-only |

### Cascade on Failure

When a Control_Objective transitions to `Failure`:

1. Warning banner added to ALL linked risk records
2. `residual_score_locked = TRUE` on all linked risks
3. Risk Analyst notified for each linked risk
4. If Failure persists > 15 business days without remediation plan → escalate to CISO
5. If ≥3 controls in Failure state in same Control_Family in same quarter → escalate as systemic issue

---

## 3. Control Activity Lifecycle (4 States)

### State Machine Diagram

```
[Draft] → [Active] ⇄ [Suspended] → [Retired]
```

### Transition Rules

| From | To | Gate Preconditions |
|---|---|---|
| Draft | Active | Approved by Control_Owner AND linked to parent objective |
| Active | Suspended | Documented rationale AND impact assessment completed |
| Suspended | Active | Suspension condition resolved |
| Active | Retired | Governance-approved. AL-1: ALL active deployments must be Decommissioned first. |
| Suspended | Retired | Governance-approved |

### Constraints

- AL-2: Draft activities CANNOT be linked to risk records (prevents premature CE evidence claims)
- Retiring an activity that has active deployments requires all deployments to be Decommissioned first (AL-1)

---

## 4. Control Deployment Lifecycle (5 States)

### State Machine Diagram

```
[Planned] → [Active] ⇄ [Degraded] ⇄ [Failed] → [Decommissioned]
```

### Transition Rules

| From | To | Gate Preconditions | Cascade |
|---|---|---|---|
| Planned | Active | Deployment confirmed on the asset | None |
| Active | Degraded | Test result = Partial OR CE drops to CE-Low | None |
| Active | Failed | Test result = Fail | DL-1: triggers Failure propagation check on parent Objective |
| Degraded | Active | Remediated AND CE re-assessed upward | None |
| Degraded | Failed | Further degradation confirmed | DL-1: triggers Failure propagation check |
| Failed | Active | Fully remediated AND evidence provided AND CE re-assessed | None |
| Failed | Decommissioned | Control permanently removed from this asset | None |
| Any | Decommissioned | Governance-approved | Record becomes READ-ONLY (DL-3) |

### CE Editability

- CE fields (rating, evidence, assessed_by) are ONLY editable when `deployment_status = Active OR Degraded` (DL-2)
- Decommissioned deployments are fully READ-ONLY (DL-3)
- CE on Planned deployments is not assessable (control is not yet operational)

> **Planned → Active carries no CE precondition, and cannot.** An earlier draft
> required "first CE assessed" to leave Planned, while DL-2 makes CE unassessable
> until the deployment is Active. That gate could never be passed. First CE is
> required one level up, at the objective's Implementation → Operating gate
> (OL-4 and CINV-1): which is the right place for it, because that is where the
> claim "this control is operating" is actually made.

---

## 5. Policy Lifecycle (6 States)

### State Machine Diagram

```
[Draft] → [Under_Review] ⇄ [Approved] → [Active] ⇄ [Under_Revision]
                                              ↓
                                        [Deprecated]
```

### Transition Rules

| From | To | Gate Preconditions | Blocking Rules |
|---|---|---|---|
| Draft | Under_Review | Policy_Owner submits for review | None |
| Under_Review | Approved | Policy_Approver (CISO+) approves. PINV-5: no self-approval. | None |
| Under_Review | Draft | Reviewer returns for revision | None |
| Approved | Active | On or after effective_date. PL-1: requires approver sign-off, effective_date, ≥1 linked control. | PINV-1: must have ≥1 linked control_objective |
| Active | Under_Revision | Triggered by: schedule, audit finding, regulatory change, risk event, >5 exceptions | PL-3: Active version remains enforceable during revision |
| Under_Revision | Approved | New version approved. PL-4: requires version increment + change_summary. | None |
| Active | Deprecated | Superseded or no longer applicable. All linked controls re-mapped. | PL-2: BLOCKED if linked control_objectives have active risk linkages ≥ Moderate. PINV-8: BLOCKED if linked risks Critical/High and unmitigated. |
| Deprecated | Under_Review | Reinstatement re-enters the approval workflow at review. It never returns directly to Active: a deprecated policy has an unreviewed control mapping and possibly a stale compliance mapping, and PINV-1 must be re-satisfied before it is enforceable again. | PINV-1 on the subsequent Approved → Active |

### Review Triggers

Unscheduled reviews triggered by: regulatory change, incident, audit finding, >5 exceptions on one policy, linked risk changes to Critical/High. Full list: [Codified Rules §13.1](./codified-rules.md).

---

## 6. Policy Exception Lifecycle (4 States)

### State Machine Diagram

```
[Requested] → [Approved] → [Expired]
            ↘ [Rejected]
```

### Transition Rules

| From | To | Gate Preconditions |
|---|---|---|
| Requested | Approved | Policy_Owner or above approves. Business justification provided. Risk statement documented. Expiry date set (PE-1: max 1yr, CISO approval for 2yr). |
| Requested | Rejected | Policy_Owner rejects with documented rationale |
| Approved | Expired | Expiry date reached OR renewal not approved |

### Automated Behaviours

- PE-2: Exception without compensating controls → auto-escalate for risk register promotion assessment
- PE-3: Systemic or prolonged exceptions → MUST promote to risk register
- PE-4: Expiry within 30 days → automatic notification to Policy_Owner + requestor
- PE-5: Expired without renewal → governance gap flagged; CISO notified

---

## 7. Threat Model Lifecycle (8 States)

### State Machine Diagram

```
[Scope] → [Decomposition] → [Threat_Analysis] → [Mitigation_Design] ⇄ [Review] ⇄ [Active] → [Deprecated]
                                                                          ↓
                                                                     [Abandoned]*

* Any state except Active can transition to [Abandoned]
```

### Transition Rules

| From | To | Gate Preconditions |
|---|---|---|
| Scope | Decomposition | Model MUST have ≥1 linked `attack_surface` asset |
| Decomposition | Threat_Analysis | Model MUST have ≥1 trust boundary or component defined |
| Threat_Analysis | Mitigation_Design | Model MUST have ≥1 identified threat scenario |
| Mitigation_Design | Review | All Critical and High severity scenarios assigned a mitigation OR flagged for risk promotion |
| Review | Mitigation_Design | Reviewer returns the model for further mitigation work. No preconditions: sending work back is never gated |
| Review | Active | `GATE_TM_SIGNOFF`: eight preconditions, below |
| Active | Review | A mitigating control failed, or the architecture changed. Sign-offs are **stripped**, not retained |
| Active | Deprecated | Feature or system decommissioned. Drops mapping to enterprise controls |
| Any except Active | Abandoned | Model abandoned before reaching Active |

### GATE_TM_SIGNOFF: Review → Active

This is the most heavily gated transition in the platform, because it is the point
at which a threat model becomes something the organisation relies on. All eight
preconditions must pass.

| # | Precondition | Invariant | What it checks |
|---|---|---|---|
| 1 | Every scenario resolved to a permitted end state | TINV-1 | Mitigated, locally Accepted (Low only), or carried by the risk register. None may remain Identified |
| 2 | Every mitigation is backed by a live control deployment | TINV-4 | A scenario marked Mitigated links to a deployment that is Active or Degraded. A planned or failed control does not mitigate |
| 3 | Sensitive components declare a trust zone | TINV-9 | A component at or above the sensitivity threshold must say where it sits. Where it sits is half of what a compromise costs |
| 4 | Every sensitive component has been analysed | TINV-11 | A component was decomposed and labelled sensitive but carries no scenario. Silence on a crown-jewel component is the one omission a scenario list cannot surface by itself |
| 5 | Every resolved scenario carries a rationale | TINV-10 | Accepting or mitigating a scenario is a decision. Record why |
| 6 | AppSec sign-off recorded | TINV-2.1 | An AppSec Lead or Engineer signs. Team membership, not a named individual |
| 7 | System Owner sign-off recorded | TINV-2.2 | The System Owner signs |
| 8 | Sign-offs are independent | TINV-2.3 | The two signatures cannot be the same person. Also enforced by `CHECK` constraint |

**On cascade:** `threat_model.activated`.

> **Sign-off is stripped, not remembered.** On `Active → Review`, both signature
> fields are cleared and `signoff_stripped_reason` records why. A model whose
> mitigating control has failed is not a signed-off model with a note attached; it
> is an unsigned model. Retaining the signatures would let the model pass straight
> back to Active on the strength of a review of a system that no longer exists.

### Scenario Status Transitions

Scenario status is not a state machine in its own right: it is derived from, and
constrained by, the link set and the rules below.

| To | Requires |
|---|---|
| Mitigated | ≥1 mitigation link, **no** link asserting `Partially_Mitigated` (TM-PARTIAL), every linked deployment Active or Degraded (TINV-4), and a rationale (TINV-10) |
| Accepted | `inherent_severity = Low` only (TINV-3), an `acceptance_expiry` ≤12 months out (TINV-5), and an acceptance rationale (TINV-10) |
| Promoted_To_Risk | A new risk record, named in `promoted_risk_id` (TINV-6). Only the one configured link type carrying `creates_risk` may do this (TINV-8) |
| Identified | The default, and the destination of every re-opening. A re-open requires a reason |

There is no `Partially_Mitigated` status. Partial coverage is derived for display
and remains an open threat.

---

## 8. Treatment Lifecycle (6 States)

Treatments hang off risks but have their own lifecycle, because a treatment is
delivered by a different person from the one who decided it was needed, which is
the whole of SEP-2 and SEP-5.

### State Machine Diagram

```
[Proposed] → [Validated] → [Approved] → [In_Progress] → [Complete]

[Any state] → [Cancelled]*

* Except Complete: a completed treatment cannot be cancelled
```

### Transition Rules

| From | To | Gate | Roles | Gate Preconditions |
|---|---|---|---|---|
| Proposed | Validated | `GATE_TREATMENT_VALIDATED` | GRC_Engineer, CISO, Admin | RINV-12.1: a named GRC Engineer confirms technical feasibility · **SEP-5**: the validator is not the treatment owner · A treatment owner is assigned |
| Validated | Approved | `GATE_TREATMENT_APPROVED` | Risk_Owner, GRC_Engineer, CISO, Admin | RINV-12.2: the treatment owner has explicitly committed · A target date is set, so the SLA clock can run · An approval decision is recorded |
| Approved | In_Progress | `GATE_TREATMENT_STARTED` | Risk_Treatment_Owner, GRC_Engineer, CISO, Admin | None |
| In_Progress | Complete | `GATE_TREATMENT_COMPLETE` | Risk_Treatment_Owner, GRC_Engineer, CISO, Admin | RESIDUAL.2: implementation evidence recorded · RESIDUAL.5: at least one progress check-in exists |
| Any except Complete | Cancelled | `GATE_TREATMENT_CANCELLED` | Risk_Owner, CISO, Admin | A cancellation reason is recorded · The treatment is not already Complete |

### Why the two-step validation

`Proposed → Validated → Approved` looks like ceremony and is not. They answer
different questions, asked of different people:

- **Validated** asks *can this be built?* A GRC Engineer answers, and they are
  technically competent to judge it and have no delivery stake in the answer.
- **Approved** asks *are we doing it, and who is accountable?* The Risk Owner
  answers, with the treatment owner's explicit commitment on record.

Collapsing them produces the most common failure in risk treatment: a plan
approved by governance that the delivery team has never agreed is achievable, which
surfaces as an SLA breach three months later.

**SEP-5** is enforced at the first step. A GRC Engineer who owns the treatment
cannot validate its feasibility, for the same reason an author does not review
their own pull request.

### Interaction with the risk lifecycle

| Event | Effect on the linked risk |
|---|---|
| Treatment reaches `Validated` and owner commits | `grc_eng_validated` and `owner_committed` satisfied, so RINV-12 unblocks Phase 4 → 5 |
| Treatment reaches `Complete` | Satisfies residual gate condition 1 on every linked risk. **Does not** update the residual score: RINV-1 still requires all five conditions |
| Treatment is `Cancelled` | Linked risks return to treatment design. The risk does not silently keep a treatment it no longer has |

> **Completion is evidence, not an outcome.** A completed treatment is one of five
> things the residual gate needs. The other four are still required, and the
> residual score does not move until all five hold. This is the same principle as
> §20.3: a cascade grants eligibility, never a result.

### Check-in immutability

`treatment_checkins` is append-only, enforced by database trigger. Progress
reporting that can be revised after the fact is not a drift trail: it is a
summary written with the benefit of hindsight, which is precisely what the record
exists to prevent.

---

## 9. Requirement Assessment Lifecycle (6 States)

Every requirement of an adopted framework carries exactly one position. This is a
Statement of Applicability, and both the decisions in it are gated: whether the
requirement applies, and whether it is covered.

### State Machine Diagram

```
[Not_Assessed] ─────→ [Applicable] ⇄ [Covered]
       │                   │  ↑          │
       │                   ↓  │          ↓
       │              [Compensating] ⇄ [Gap]
       ↓                                 ↑
[Not_Applicable] ──→ [Applicable] ───────┘
```

### Transition Rules

| From | To | Gate | Roles | Gate Preconditions |
|---|---|---|---|---|
| Not_Assessed | Applicable | `GATE_REQUIREMENT_IN_SCOPE` | Assessor | **AINV-8**: the framework is adopted |
| Not_Assessed | Not_Applicable | `GATE_REQUIREMENT_EXCLUDED` | Approver | **AINV-1**: a documented justification |
| Not_Applicable | Applicable | `GATE_REQUIREMENT_IN_SCOPE` | Approver | A reason for re-scoping: reversing an exclusion changes the SoA |
| Applicable | Covered | `GATE_REQUIREMENT_COVERED` | Assessor | **AINV-2**: a satisfying link, an Operating objective, a live deployment inside scope |
| Applicable | Compensating | `GATE_REQUIREMENT_COMPENSATING` | Approver | **AINV-4**: a compensating link, an expiry within the window, and a rationale |
| Applicable | Gap | `GATE_REQUIREMENT_GAP` | Assessor | None |
| Covered | Gap | `GATE_REQUIREMENT_GAP` | Assessor | None. Fired automatically by the §24.3 cascade |
| Covered | Applicable | `GATE_REQUIREMENT_REASSESS` | Assessor | None. Re-opened, for instance on a framework version change |
| Compensating | Covered | `GATE_REQUIREMENT_COVERED` | Assessor | **AINV-2**: a permanent control replaced the compensating one |
| Compensating | Gap | `GATE_REQUIREMENT_GAP` | Assessor | None. Expiry or withdrawal |
| Gap | Covered | `GATE_REQUIREMENT_COVERED` | Assessor | **AINV-2**: closing a gap means the control runs, not that it is planned |
| Gap | Compensating | `GATE_REQUIREMENT_COMPENSATING` | Approver | **AINV-4** |

**Assessor:** Risk_Analyst, GRC_Engineer, Control_Owner, CISO, Admin.
**Approver:** GRC_Engineer, CISO, Admin. Excluding a requirement or resting on a
compensating control are governance decisions, not assessment work, so they sit
at the higher band.

### Why `Not_Assessed` is a state

It would be simpler to treat an unassessed requirement as a missing row. It would
also make the most common state in any real register invisible, and a register
that cannot count what nobody has looked at will report a flattering number on
its first day. A framework with 106 requirements and 4 positions is 4% assessed,
and that is the honest headline.

### There is no `Partially_Covered` state

Partial coverage is derived from the link set and displayed as detail on the
requirement. Giving it a status would let it satisfy an audit position, which is
the same reason there is no `Partially_Mitigated` threat status (TM-PARTIAL).

---

## 10. Cross-Lifecycle Cascade Rules

State changes in one lifecycle propagate to related entities. These cascades are the mechanism by which the platform maintains consistency across interconnected state machines.

### Control → Risk Cascades

| Trigger | Source Lifecycle | Target Lifecycle | Cascade Behaviour | SLA |
|---|---|---|---|---|
| CE degradation | Control Deployment | Risk | Risk flagged "Control Changed: Re-evaluation Required". Risk Analyst notified. | Critical: 5bd, High: 10bd, Moderate: 20bd, Mod-Low: 30bd |
| CE improvement | Control Deployment | Risk | Risk flagged "Control Improved: Residual Update Eligible". Full validation gate (§4.7) still required. | Analyst-triggered; no automatic score update |
| Control → Failure | Control Objective | Risk | Warning banner on ALL linked risk records. `residual_score_locked = TRUE`. | Immediate. Escalation at 15bd if unresolved. |
| Control → Deprecated | Control Objective | Risk | Risk Analyst notified. Risk re-assessment required if control was contributing to residual scoring. | 30bd for re-assessment |

### Policy → Control Cascades

| Trigger | Source Lifecycle | Target Lifecycle | Cascade Behaviour | SLA |
|---|---|---|---|---|
| Policy revision | Policy | Control Objective | All linked Control_Objectives flagged for re-alignment check. Control_Owners notified. | 30 days for alignment confirmation |
| Policy deprecation | Policy | Control Objective | All linked Control_Objectives flagged for re-mapping to surviving policy. | 60 days for re-mapping |
| Standard revision | Standard (child of Policy) | Control Activity | All linked Control_Activity owners notified. Alignment confirmation required. | 30 days |

### Issue → Control → Risk Cascades

| Trigger | Source | Intermediate | Target | Cascade Behaviour |
|---|---|---|---|---|
| Control test failure | Control Deployment | Issue auto-created | Risk | Issue created linked to deployment (CI-1). CE re-assessment triggered (CI-2). If issue breaches SLA → evaluate for risk promotion (CI-3). |
| Issue remediation | Issue | Control Deployment | Risk | CE re-assessment on linked deployment. If CE improves and linked risk has locked residual → risk flagged as eligible for update. |

### Threat Model → Risk Cascades

| Trigger | Source | Intermediate | Target | Cascade Behaviour |
|---|---|---|---|---|
| Control test failure | Control Deployment | Threat Scenario | Threat Model & Risk | TINV-4: Failed control immediately re-opens the `Threat_Scenario` to 'Identified'. Threat model transitions from Active back to Review. `System_Owner` notified. If unaddressed > 15bd AND severity ≥ Medium → auto-promotes to formal Risk. |
| Threat scenario unmitigated | Threat Scenario | None | Risk | A scenario with no mitigation assigned and not eligible for local Low acceptance is promoted to the register (§20.1). TINV-8 first checks whether an existing risk already carries the exposure: if one does, the scenario is *linked*, not promoted, and the register gains no duplicate. |
| **Threat scenario mitigated** | Threat Scenario | None | Risk | §20.3, the mirror of the row above. Every risk record carrying the scenario, whether by `promoted_risk_id` or by a risk link, is flagged `Linked_Threat_Mitigated`. Risk Owner and Risk Analyst notified. **The residual score is not updated:** RINV-1 still requires all five conditions. |

> **The loop runs both ways, and neither direction moves a number.** A control
> failure re-opens a threat and freezes the residual; a mitigation makes the risk
> eligible for re-evaluation. Both directions grant or revoke *eligibility*. A
> score changes only when a person passes the gate that RINV-1 defines, which is
> what stops the cascade engine from quietly re-rating the register overnight.

### Control → Compliance Cascades

| Trigger | Source | Target | Cascade Behaviour |
|---|---|---|---|
| Control → Failure | Control Objective | Requirement Assessment | **AINV-5**. Every requirement covered by a satisfying link to that control returns to `Gap`, with `gap_reason` naming the control. Skipped where another Operating control still satisfies the requirement |
| Control → Deprecated | Control Objective | Requirement Assessment | Same, with a re-mapping prompt: retiring a control that carries an audit position is a governance event, not a tidy-up |

> **Why the "another Operating control" clause matters.** Revoking coverage a
> second control still provides would report a gap that does not exist. A
> compliance figure loses trust faster from one false alarm than from a missed
> finding, and a figure nobody trusts gets replaced by a spreadsheet.

### Acceptance Expiry Cascade

| Trigger | Cascade Behaviour |
|---|---|
| `acceptance_expiry` date reached | Risk auto-flagged as Above Appetite. Escalation: Risk_Owner → Risk_Stakeholder → CISO. Risk returns to Phase 2 for re-assessment. No silent expiry permitted (RINV-11). |

---

## Implementation Notes

### Gate Enforcement Pattern

All gates follow the same implementation pattern:

```
function check_gate(entity_id, target_state):
    entity = load(entity_id)
    gate = GATES[entity.current_state → target_state]

    if gate is None:
        reject("Invalid transition: {current} → {target} is not a valid path")

    for precondition in gate.preconditions:
        if not precondition.evaluate(entity):
            reject("Gate blocked: {precondition.name} not satisfied")

    entity.state = target_state
    entity.updated_at = now()
    audit_log.record(entity_id, "state_transition", target_state, actor)

    for cascade in gate.cascades:
        cascade.execute(entity)

    return entity
```

### Audit Trail

Every state transition MUST be recorded in the audit log with: entity ID, previous state, new state, timestamp, actor (user or system), and gate evaluation result (which preconditions were checked and their values).

---

*This reference is released under CC BY 4.0. Adapt freely with attribution.*
