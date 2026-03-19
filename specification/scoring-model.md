# Risk Scoring Model

**Version:** 2.0-template | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](./codified-rules.md) §4
**Purpose:** Complete specification of the risk scoring model including the 5x5 matrix, impact and likelihood definitions, control effectiveness adjustment, residual scoring validation, and all FK dependencies that feed the calculation. Designed for implementation teams to build the scoring engine with full traceability from input to output.

> **Design principle:** The scoring engine is deterministic. Given the same inputs, it must produce the same output every time. There is no discretionary override. Every adjustment is traceable to an evidence-backed input.

---

## Table of Contents

1. [Scoring Overview](#1-scoring-overview)
2. [Impact Scale (5-level)](#2-impact-scale-5-level)
3. [Likelihood Scale (5-level)](#3-likelihood-scale-5-level)
4. [Inherent Risk Calculation](#4-inherent-risk-calculation)
5. [Control Effectiveness Model](#5-control-effectiveness-model)
6. [Residual Risk Calculation](#6-residual-risk-calculation)
7. [Residual Validation Gate](#7-residual-validation-gate)
8. [Scoring Preconditions](#8-scoring-preconditions)
9. [FK Dependencies](#9-fk-dependencies)
10. [Scoring Engine Rules](#10-scoring-engine-rules)

---

## 1. Scoring Overview

### Formula

```
INHERENT_RISK_SCORE  = IMPACT × LIKELIHOOD                     # Range: 1-25
RESIDUAL_RISK_SCORE  = RESIDUAL_IMPACT × RESIDUAL_LIKELIHOOD   # Range: 1-25
```

### Rating Bands

| Score Range | Rating | Appetite Status | Required Action |
|---|---|---|---|
| 20-25 | **Critical** | Above Appetite | Mandatory immediate mitigation. Cannot be accepted (RINV-5). |
| 15-19 | **High** | Above Appetite | Mandatory mitigation. Acceptance requires C-level approval, max 90 days. |
| 10-14 | **Moderate** | Above Appetite | Mitigate or accept. Acceptance requires VP+ approval, max 180 days. |
| 5-9 | **Moderate-Low** | At Appetite | Monitor and review. Acceptance requires Director+ approval, max 360 days. |
| 1-4 | **Low** | Within Appetite | Monitor only. Acceptance at Risk_Owner discretion, annual review. |

### 5x5 Scoring Matrix

```
                Impact →    1(Minimal) 2(Low)   3(Mod)   4(High)  5(Critical)
Likelihood ↓
5 (Almost Certain)          5         10       15       20       25
4 (Likely)                  4          8       12       16       20
3 (Possible)                3          6        9       12       15
2 (Unlikely)                2          4        6        8       10
1 (Rare)                    1          2        3        4        5
```

---

## 2. Impact Scale (5-level)

Impact measures the consequence of the risk event materialising. It is scored independently of likelihood and is not adjusted by control effectiveness.

| Score | Label | Description | Indicative Characteristics |
|---|---|---|---|
| 5 | **Critical** | Existential or near-existential consequence | Prolonged systemic outage. Licence revocation. Critical data breach (>100k clients). Material regulatory sanction. Significant share price impact. |
| 4 | **High** | Major disruption to business operations | Significant SLA breach. Regulatory enforcement action. Major reputational damage. Material financial loss. Key client loss. |
| 3 | **Moderate** | Manageable disruption | Localised service impact. Audit finding requiring remediation. Moderate financial loss. Contained reputational impact. |
| 2 | **Low** | Minor operational impact | Limited operational effect. Minor compliance gap. Low financial exposure. No client impact. |
| 1 | **Minimal** | Negligible consequence | No measurable operational, financial, or regulatory consequence. |

### Impact Scoring Rules

```
RULE IMP-1: Impact is scoped by Risk_Tier
  Tier 1 (Organisation):       consider enterprise-wide blast radius
  Tier 2 (Mission/Process):    consider business process scope
  Tier 3 (Information System): consider single system/platform scope
  Tier 4 (Component):          consider component-level scope

RULE IMP-2: Impact justification REQUIRED for every score
  Must include: risk_tier_scope_boundary, business_impact_category, rationale_within_scope

RULE IMP-3: Select the highest Risk_Tier credibly impacted
  Consider shared dependencies and systemic blast radius
  A Tier 4 component failure that cascades to Tier 1 impact should be scored at Tier 1

RULE IMP-4: Impact is NOT adjusted by Control Effectiveness
  Controls reduce LIKELIHOOD, not impact. The consequence of the event does not change
  because you have a control in place. The probability does.
```

---

## 3. Likelihood Scale (5-level)

Likelihood measures the probability of the risk event occurring within the assessment period, considering the current control environment.

| Score | Label | Description | Indicative Frequency |
|---|---|---|---|
| 5 | **Almost Certain** | Expected to occur within the assessment period. Has occurred recently. | Multiple times per year or continuous exposure |
| 4 | **Likely** | High probability. Strong indicators or precedent in sector. | Expected within 12 months |
| 3 | **Possible** | Could occur. Some enabling conditions present. | Plausible within 1-3 years |
| 2 | **Unlikely** | Not expected but plausible under specific conditions. | Conceivable within 3-5 years |
| 1 | **Rare** | Exceptional circumstances only. No credible current threat path. | Would require extraordinary conditions |

### Likelihood Scoring Rules

```
RULE LKH-1: Likelihood is informed by Control Effectiveness (CE)
  CE-High      → reduce likelihood 1-2 levels (justified by evidence)
  CE-Medium    → reduce likelihood 0-1 level
  CE-Low       → NO reduction
  CE-Unvalidated → NO reduction (treated as CE-Low)

RULE LKH-2: CE adjustment requires documented justification
  The Risk_Analyst must document which controls were considered,
  what CE rating was applied, and why the likelihood reduction is appropriate.

RULE LKH-3: Inherent likelihood is scored WITHOUT CE adjustment
  Inherent = "what would the likelihood be with NO controls in place?"
  CE adjustment applies only to residual likelihood calculation.
```

---

## 4. Inherent Risk Calculation

Inherent risk represents the exposure before any controls or treatments are applied.

```
INHERENT_RISK_SCORE = INHERENT_IMPACT × INHERENT_LIKELIHOOD

WHERE:
  INHERENT_IMPACT     = impact score (1-5) based on business consequence (§2)
  INHERENT_LIKELIHOOD = likelihood score (1-5) WITHOUT CE adjustment (LKH-3)

OUTPUT:
  INHERENT_SCORE  = integer (1-25)
  INHERENT_RATING = derived from rating bands (§1)
```

### Inherent Scoring Constraints

```
CONSTRAINT: scoring CANNOT begin until all preconditions are met (§8, RINV-8)
CONSTRAINT: Risk_Owner and Risk_Stakeholder MUST be assigned before scoring (RINV-10)
CONSTRAINT: Risk_Tier MUST be assigned before scoring
CONSTRAINT: inherent scores are IMMUTABLE once the risk advances past Phase 3
  (re-assessment creates a new scoring cycle, not an edit to the existing score)
```

---

## 5. Control Effectiveness Model

Control Effectiveness (CE) is the evidence-backed assessment of how well existing controls reduce the likelihood of a risk event.

### CE Ratings

| Rating | Definition | Evidence Standard | Likelihood Adjustment |
|---|---|---|---|
| **CE-High** | Effective and consistently operating. Automated, continuous monitoring, strong coverage. | Current configs, active dashboards, recent test passes, automated alerts operational. | Reduce 1-2 levels |
| **CE-Medium** | Present but partially effective. Mixed automation, partial coverage, known gaps. | Partial coverage evidence, some manual processes, gaps documented. | Reduce 0-1 level |
| **CE-Low** | Limited reduction. Mostly manual, retrospective, inconsistent. | Evidence exists but demonstrates inconsistent operation or narrow coverage. | No reduction |
| **CE-Unvalidated** | No current evidence. Default state. | No evidence provided OR evidence has expired. | No reduction (treated as CE-Low) |

### CE Assessment Rules

```
RULE CE-1: CE-Unvalidated is the DEFAULT state
  Every control deployment starts at CE-Unvalidated until evidence is provided.

RULE CE-2: CE assessment REQUIRES documented evidence
  Acceptable evidence: configurations, logs, dashboards, audit artefacts,
  test results, automated scan outputs. Verbal attestation is NOT sufficient.

RULE CE-3: CE is assessed PER DEPLOYMENT, not per control objective
  A single control objective may have multiple deployments across different assets.
  Each deployment has its own CE rating reflecting operational reality on that asset.

RULE CE-4: WORST-CASE CE feeds risk scoring
  If a control has deployments with CE-High, CE-Medium, and CE-Low,
  the CE used for risk scoring is CE-Low (the worst case).
  Never average. Never use best-case. (CINV-6)

RULE CE-5: only OPERATING controls contribute CE
  Controls in Design, Implementation, Redesign, or Deprecated state
  are excluded from scoring calculations. (CINV-2)
  Planned controls do not reduce residual risk. (RINV-9)
```

### CE Expiry

CE ratings are not permanent. They expire based on the control's operating frequency:

| Control Frequency | CE Expiry Period |
|---|---|
| Continuous | 2 months without re-assessment |
| Monthly | 6 months |
| Quarterly | 12 months |
| Annual | 24 months |

```
RULE CE-6: expired CE auto-downgrades to CE-Unvalidated
  No manual override permitted. (CINV-10)
  Risk Analyst notified when CE expires on controls linked to active risks.
```

### CE Change Triggers

```
TRIGGER: CE rating degrades on any deployment linked to a risk
  ACTION: risk flagged "Control Changed — Re-evaluation Required"
  SLA:    Critical risk: 5bd | High: 10bd | Moderate: 20bd | Mod-Low: 30bd

TRIGGER: CE rating improves on deployment linked to a risk with locked residual
  ACTION: risk flagged "Control Improved — Residual Update Eligible"
  NOTE:   full residual validation gate (§7) still required before score update
```

---

## 6. Residual Risk Calculation

Residual risk represents the remaining exposure after controls and treatments have been applied and validated.

```
RESIDUAL_RISK_SCORE = RESIDUAL_IMPACT × RESIDUAL_LIKELIHOOD

WHERE:
  RESIDUAL_IMPACT     = impact score (1-5), adjusted if treatment reduces blast radius
  RESIDUAL_LIKELIHOOD = likelihood score (1-5), adjusted by validated CE per §5
```

### Residual Scoring Rules

```
RULE RES-1: residual score fields are LOCKED by default
  Fields become editable ONLY when the residual validation gate (§7) passes.
  Until then, residual remains at inherent score. (RINV-1)

RULE RES-2: risks under active treatment remain "Acknowledged at Inherent Risk"
  The inherent score is the reported score until mitigations are complete
  and validated. No interim residual updates.

RULE RES-3: residual impact CAN differ from inherent impact
  Treatments that reduce blast radius (e.g. network segmentation, data
  minimisation) may justify a lower residual impact score. Must be documented.

RULE RES-4: residual likelihood MUST reflect validated CE
  The CE adjustment applied to residual likelihood must reference the
  CE ratings of controls that are: (a) in Operating state, (b) with
  non-expired CE, (c) using worst-case CE across deployments.

RULE RES-5: CE snapshot is recorded at assessment time
  The risk_controls join table stores ce_at_assessment. Subsequent CE
  changes flag the risk for re-evaluation but do NOT auto-update the
  residual score. Re-evaluation requires a deliberate scoring cycle.
```

---

## 7. Residual Validation Gate

The residual validation gate is the most critical enforcement point in the scoring model. It ensures residual scores are never updated based on intent, only on evidence.

### Gate: `GATE_RESIDUAL_VALIDATED`

All 5 conditions must be TRUE simultaneously:

| # | Condition | Evidence Required | Validates |
|---|---|---|---|
| 1 | Mitigations fully implemented | Treatment status = Complete on all linked risk_treatments | Controls are operational, not planned |
| 2 | Evidence provided | `evidence_ref` non-empty; artefacts attached (configs, logs, dashboards, audit records) | Claims are backed by proof |
| 3 | Treatment effectiveness confirmed | Risk_Analyst has reviewed evidence and confirmed effectiveness | Independent validation, not self-assessment |
| 4 | Governance approval documented | Approval record with approver identity and timestamp | Decision is authorised |
| 5 | Risk drift tracked | Drift log shows inherent-vs-residual delta over treatment period | No silent degradation during treatment |

### Gate Behaviour

```
IF all 5 conditions = TRUE:
  → residual_score_locked = FALSE
  → residual impact, likelihood, score, rating fields become editable
  → Risk_Analyst completes residual scoring
  → risk advances to Phase 7 (Monitoring)

IF any condition = FALSE:
  → residual remains at INHERENT score
  → residual fields remain READ-ONLY
  → risk stays in Phase 6
  → specific failing condition(s) surfaced to Risk_Analyst
```

---

## 8. Scoring Preconditions

No scoring can begin until all preconditions are satisfied. This is enforced at the Phase 2 → Phase 3 gate.

### Precondition Checklist

| # | Precondition | Validates | Spec Ref |
|---|---|---|---|
| 1 | True risk confirmed | Item has passed triage and meets risk criteria (not an issue, not out-of-scope) | §3.6 |
| 2 | Risk tier assigned | NIST RMF tier (1-4) assigned with documented rationale | §3.7 |
| 3 | All stakeholders identified | Risk_Owner, Risk_Analyst, Risk_Treatment_Owner, Control_Owner(s), Control_Operator(s) all assigned | §2.1 |
| 4 | Control effectiveness assessed | At least one linked control has a non-Unvalidated CE rating with evidence | §4.5 |

```
ENFORCEMENT: Phase 2 gate checks all 4 items.
  All must return TRUE before scoring fields become editable.
  VIOLATION: scoring_without_preconditions → NON_COMPLIANT (RINV-8)
```

---

## 9. FK Dependencies

The scoring engine depends on data from multiple related entities. This section maps every FK dependency so implementation teams understand which tables and relationships must be resolved before the scoring engine can execute.

### Inherent Scoring Dependencies

```
risks
  ├── risk_tier              (local field, required before scoring)
  ├── risk_owner_id          (FK → users, NOT NULL, RINV-10)
  ├── risk_stakeholder_id    (FK → users, NOT NULL, RINV-10)
  ├── inherent_impact        (local field, scored by Risk_Analyst)
  └── inherent_likelihood    (local field, scored by Risk_Analyst)
```

### Residual Scoring Dependencies

```
risks
  ├── inherent_score         (must be computed first)
  │
  ├── risk_controls          (join table, M:M)
  │   ├── control_id         (FK → control_objectives)
  │   ├── ce_at_assessment   (snapshot, recorded at scoring time)
  │   └── control_objectives
  │       ├── lifecycle_status   (MUST = Operating to contribute CE, CINV-2)
  │       └── control_deployments
  │           ├── ce_rating          (per-deployment CE, worst-case used, CINV-6)
  │           ├── ce_last_assessed   (must not be expired per CE expiry rules)
  │           └── deployment_status  (MUST = Active or Degraded for CE to be valid)
  │
  ├── risk_treatments        (join table, 1:N)
  │   ├── status             (must = Complete for residual gate)
  │   ├── grc_eng_validated  (must = TRUE, RINV-12)
  │   ├── owner_committed    (must = TRUE, RINV-12)
  │   └── control_mapping    (FK[] → control_objectives, if Mitigate)
  │
  └── RESIDUAL_VALIDATION_GATE (all 5 conditions, §7)
      → residual_impact
      → residual_likelihood
      → residual_score (computed)
      → residual_rating (derived)
```

### CE Resolution Order

The scoring engine MUST resolve CE before computing residual likelihood. This is a strict ordering constraint that prevents circular dependencies:

```
STEP 1: Resolve CE for each linked control
  → Query all control_deployments for each linked control_objective
  → Filter: deployment_status IN (Active, Degraded)
  → Filter: lifecycle_status = Operating on parent objective
  → Filter: ce_last_assessed not expired per CE expiry rules
  → Select: MIN(ce_rating) across qualifying deployments (worst-case, CINV-6)

STEP 2: Apply CE to likelihood
  → Use CE-to-likelihood adjustment table (§5)
  → Document which controls contributed and what adjustment was applied

STEP 3: Compute residual score
  → RESIDUAL_SCORE = RESIDUAL_IMPACT × RESIDUAL_LIKELIHOOD
  → Derive RESIDUAL_RATING from rating bands

CRITICAL: CE calculation (Step 1) MUST resolve before scoring (Step 3).
  Circular dependency between scoring and CE is prohibited.
  CE is a fixed input to the scoring engine, never derived from it.
```

---

## 10. Scoring Engine Rules

Summary of all rules that the scoring engine must enforce, consolidated for implementation reference.

### Input Rules

| Rule ID | Rule | Source |
|---|---|---|
| IMP-1 | Impact scoped by Risk_Tier | §2 |
| IMP-4 | Impact NOT adjusted by CE | §2 |
| LKH-1 | Likelihood adjusted by CE (High: -1 to -2, Medium: 0 to -1, Low/Unvalidated: 0) | §3 |
| LKH-3 | Inherent likelihood scored WITHOUT CE adjustment | §3 |
| CE-4 | Worst-case CE across deployments used (never average, never best-case) | §5 |
| CE-5 | Only Operating controls with non-expired CE contribute | §5 |

### Calculation Rules

| Rule ID | Rule | Source |
|---|---|---|
| CALC-1 | Score = Impact × Likelihood (both inherent and residual) | §1 |
| CALC-2 | Rating derived from score bands (1-4: Low, 5-9: Mod-Low, 10-14: Mod, 15-19: High, 20-25: Critical) | §1 |
| CALC-3 | CE resolves before residual likelihood; no circular dependencies | §9 |
| CALC-4 | CE snapshot recorded in risk_controls join at assessment time | §9 |

### Output Rules

| Rule ID | Rule | Source |
|---|---|---|
| OUT-1 | Residual fields locked until validation gate passes (RINV-1) | §7 |
| OUT-2 | Risks under treatment remain at inherent score (RES-2) | §6 |
| OUT-3 | Planned/unvalidated controls excluded from calculation (RINV-9) | §5 |
| OUT-4 | Critical risks cannot have treatment_decision = Accept (RINV-5) | §1 |
| OUT-5 | Inherent scores immutable once risk advances past Phase 3 | §4 |

---

*This scoring model is released under CC BY 4.0. Adapt freely with attribution.*
