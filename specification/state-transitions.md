# State Transitions Reference

**Version:** 2.0-template | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](./codified-rules.md) §4-§5 (Risk), §9 (Controls), §13 (Policy)
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
7. [Cross-Lifecycle Cascade Rules](#7-cross-lifecycle-cascade-rules)

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
| Design | Implementation | ≥1 Control_Activity defined AND deployment plan exists | — |
| Implementation | Operating | All target deployments in Active state AND first CE assessed | OL-4: requires ≥1 active deployment |
| Operating | Failure | CE-Low on critical deployment OR test result = Fail on any deployment | — |
| Failure | Operating | Remediated without architectural change AND CE re-assessed upward | — |
| Failure | Redesign | Remediation requires architectural change to control design | — |
| Redesign | Implementation | Redesigned and ready for re-deployment | — |
| Operating | Deprecated | Governance-approved retirement | OL-3: BLOCKED if linked risks ≠ {Closed, Accepted, Transferred} |
| Any | Deprecated | With documented rationale + Risk_Owner notification for linked risks | OL-3 applies |

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
| Planned | Active | Deployment confirmed AND first CE assessed | — |
| Active | Degraded | Test result = Partial OR CE drops to CE-Low | — |
| Active | Failed | Test result = Fail | DL-1: triggers Failure propagation check on parent Objective |
| Degraded | Active | Remediated AND CE re-assessed upward | — |
| Degraded | Failed | Further degradation confirmed | DL-1: triggers Failure propagation check |
| Failed | Active | Fully remediated AND evidence provided AND CE re-assessed | — |
| Failed | Decommissioned | Control permanently removed from this asset | — |
| Any | Decommissioned | Governance-approved | Record becomes READ-ONLY (DL-3) |

### CE Editability

- CE fields (rating, evidence, assessed_by) are ONLY editable when `deployment_status = Active OR Degraded` (DL-2)
- Decommissioned deployments are fully READ-ONLY (DL-3)
- CE on Planned deployments is not assessable (control is not yet operational)

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
| Draft | Under_Review | Policy_Owner submits for review | — |
| Under_Review | Approved | Policy_Approver (CISO+) approves. PINV-5: no self-approval. | — |
| Under_Review | Draft | Reviewer returns for revision | — |
| Approved | Active | On or after effective_date. PL-1: requires approver sign-off, effective_date, ≥1 linked control. | PINV-1: must have ≥1 linked control_objective |
| Active | Under_Revision | Triggered by: schedule, audit finding, regulatory change, risk event, >5 exceptions | PL-3: Active version remains enforceable during revision |
| Under_Revision | Approved | New version approved. PL-4: requires version increment + change_summary. | — |
| Active | Deprecated | Superseded or no longer applicable. All linked controls re-mapped. | PL-2: BLOCKED if linked control_objectives have active risk linkages ≥ Moderate. PINV-8: BLOCKED if linked risks Critical/High and unmitigated. |
| Deprecated | Active | Reinstatement: requires full approval workflow | — |

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

## 7. Cross-Lifecycle Cascade Rules

State changes in one lifecycle propagate to related entities. These cascades are the mechanism by which the platform maintains consistency across interconnected state machines.

### Control → Risk Cascades

| Trigger | Source Lifecycle | Target Lifecycle | Cascade Behaviour | SLA |
|---|---|---|---|---|
| CE degradation | Control Deployment | Risk | Risk flagged "Control Changed — Re-evaluation Required". Risk Analyst notified. | Critical: 5bd, High: 10bd, Moderate: 20bd, Mod-Low: 30bd |
| CE improvement | Control Deployment | Risk | Risk flagged "Control Improved — Residual Update Eligible". Full validation gate (§4.7) still required. | Analyst-triggered; no automatic score update |
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
