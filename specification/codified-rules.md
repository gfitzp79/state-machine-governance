# GRC Codified Rules Engine — Unified Specification Template

**Version:** 2.0-template | **License:** CC BY 4.0
**Purpose:** Machine-parseable rule set for governance, risk, and compliance platforms. Covers the risk management lifecycle, control management hierarchy, and policy governance layer as a single integrated specification. Designed for organisations to adapt to their own frameworks, appetite statements, and regulatory obligations.

> **How to use this document:** Replace all `[ORGANISATION]` placeholders and review every `[CUSTOMISE]` block against your own governance framework, regulatory requirements, and risk appetite. Parameters marked `RECOMMENDED` reflect industry best practice from ISO 27005, NIST RMF, NIST CSF, and SOC 2/COSO. SLA defaults are aligned to regulated financial services expectations. Adjust thresholds to match your operating environment.

---

# PART 1: RISK MANAGEMENT

## §1 FRAMEWORK SCOPE

### §1.1 Applicability

```
SCOPE := all { organizational_units, systems, environments, business_processes,
               [CUSTOMISE: add third_party_relationships if TPRM module is deployed] }
  WHERE handles_sensitive_data = TRUE
  OR impacts IN [CUSTOMISE: e.g. Revenue, Regulatory_Standing, Operational_Continuity, Client_Trust]
```

### §1.2 Risk Appetite

```
# [CUSTOMISE] Define appetite per risk domain. Recommended: separate enterprise and cyber appetite.
ENTERPRISE_APPETITE := [CUSTOMISE: e.g. Moderate]
CYBER_APPETITE      := [CUSTOMISE: e.g. Low]

APPETITE_THRESHOLDS (5x5 matrix):
  score IN [20,25] → rating=Critical,      status=Above_Appetite, action=MANDATORY_IMMEDIATE_MITIGATION
  score IN [15,19] → rating=High,          status=Above_Appetite, action=MANDATORY_MITIGATION
  score IN [10,14] → rating=Moderate,      status=Above_Appetite, action=MITIGATE_OR_ACCEPT
  score IN [5,9]   → rating=Moderate-Low,  status=At_Appetite,    action=MONITOR_AND_REVIEW
  score IN [1,4]   → rating=Low,           status=Within_Appetite, action=MONITOR_ONLY
```

### §1.3 Framework Alignment

```
ALIGNED_TO := [CUSTOMISE: e.g. { ISO_27005, NIST_RMF, SOC2_COSO, NIST_CSF, DORA }]
```

---

## §2 ROLES AND SEPARATION OF DUTIES

### §2.1 Role Definitions

```
ROLE Risk_Owner:
  type: accountable_decision_maker
  responsibilities: [own_risk_decision, approve_treatment_or_acceptance, ensure_appetite_alignment, accountable_for_residual]

ROLE Risk_Stakeholder:
  type: senior_oversight ([CUSTOMISE: e.g. VP+, C-level])
  responsibilities: [enterprise_alignment, escalation_participation, acceptance_oversight]
  CONSTRAINT: assigned_to EVERY risk regardless of severity

ROLE Risk_Analyst:
  type: governance_execution
  responsibilities: [assessment_scoring, control_validation, sla_tracking, escalation, governance_reporting]

ROLE GRC_Engineer:
  type: technical_governance
  responsibilities: [treatment_validation, treatment_feasibility_assessment, control_design_support,
                     tooling_integration, specification_development, automation_design]
  CONSTRAINT: engaged during treatment design to validate technical viability and control mapping

ROLE Risk_Treatment_Owner:
  type: delivery_accountability
  responsibilities: [execute_mitigation_plan, coordinate_delivery, report_progress_and_blockers]

ROLE Control_Owner:
  type: control_design_effectiveness
  responsibilities: [design_maintain_controls, provide_effectiveness_evidence, support_remediation]

ROLE Control_Operator:
  type: operational_execution
  responsibilities: [implement_operate_controls, support_evidence_collection]

ROLE Security_SME:
  type: subject_matter_advisory
  responsibilities: [threat_landscape_context, technical_risk_assessment_support, treatment_architecture_guidance,
                     control_design_review, security_tooling_evaluation]
  CONSTRAINT: consulted on High and Critical risks during assessment and treatment design
```

### §2.2 Separation Rules (MANDATORY)

```
RULE SEP-1: Risk_Owner ≠ Risk_Stakeholder
RULE SEP-2: Risk_Owner ≠ Risk_Treatment_Owner       # decision maker ≠ executor
RULE SEP-3: Control_Owner MUST_NOT influence risk_scoring OR acceptance_decisions
RULE SEP-4: Governance_oversight ≠ operational_delivery
RULE SEP-5: GRC_Engineer MUST_NOT unilaterally approve risk acceptance decisions

VIOLATION(SEP-*) → governance_weakness → ESCALATE
```

### §2.3 Ownership by Severity

```
# [CUSTOMISE] Align minimum ownership levels to your organisational hierarchy.
# RECOMMENDED for regulated financial services:
OWNERSHIP_MATRIX:
  Critical     → min_level: C-level / ExCo member
  High         → min_level: VP+
  Moderate     → min_level: Senior_Director+
  Moderate-Low → min_level: Director
  Low          → min_level: Director
```

---

## §3 RISK IDENTIFICATION

### §3.1 Structured Risk Statement (MANDATORY FORMAT)

```
RISK_STATEMENT := {
  cause:         string,   # underlying condition or threat source
  threat_event:  string,   # exploiting scenario
  vulnerability: string,   # control gap enabling the threat
  impact:        string    # MUST reference business impact, NOT just technical failure
}

# RECOMMENDED: Use "Because [cause], there is a risk that [threat_event]
# exploits [vulnerability], resulting in [impact]" as the canonical pattern.
```

### §3.2 Intake Sources (AUTHORITATIVE)

```
VALID_INTAKE := {
  risk_assessments,                    # targeted, thematic, or periodic risk assessments
  audit_findings,                      # internal audit, external audit, regulatory examination
  issue_management_escalations,        # issues promoted from control failures (per §3.6)
  vulnerability_management,            # critical/high vulnerabilities breaching SLA or systemic
  incident_management,                 # post-incident risk identification and lessons learned
  threat_intelligence,                 # external threat landscape changes, sector alerts, advisories
  regulatory_change,                   # new or amended regulatory requirements, supervisory feedback
  third_party_risk_management,         # risks identified through third-party assessments or external dependency reviews
  policy_exception_management,         # material, systemic, or prolonged policy exceptions
  business_change,                     # M&A, new product launch, market entry, technology migration
  continuous_monitoring,               # SIEM alerts, control monitoring, posture drift detection
  self_identification                  # business unit or function self-reported risk
}
```

### §3.3 Triage Rules

```
TRIAGE(item):
  IF is_true_risk(item) → RISK_REGISTER_ADMISSION
  ELSE → ALTERNATE_GOVERNANCE

  DECISION must_be DOCUMENTED for audit_traceability
```

### §3.4 Out-of-Scope Categories

```
# [CUSTOMISE] Adjust categories to match your operating model.
OUT_OF_SCOPE := {
  individual_control_failures,   # → Issue Management unless systemic or out-of-SLA
  project_delivery_risks,        # → Project Risk Register
  bau_operational_risks,         # unless creates material exposure
  tooling_vendor_delays,         # unless unmonitored assets or systems result
  resource_constraints,          # capacity risk, not cyber risk
  change_management_gaps,        # unless audit failure or systemic exposure
  legacy_upgrade_delays          # unless material attack path created
}
```

### §3.5 Promotion to Risk Register

```
PROMOTE(out_of_scope_item) WHEN:
  reveals_systemic_control_weakness = TRUE
  OR produces_material_exposure = TRUE
  OR breaches_sla_with_elevated_impact = TRUE
  OR requires_enterprise_governance = TRUE

POST_PROMOTE: create_risk_record + assign_risk_owner + structured_risk_statement
```

### §3.6 Issue vs Risk

```
ISSUE := failed or ineffective control identified through testing, monitoring, audit, or incident
  ROUTE → Issue_Management
  NOT displayed in risk register dashboards unless promoted
  TRACKED with: remediation_owner, target_date, severity, linked_control, linked_risk (optional)

RISK := material_cyber_exposure requiring business_level_accountability + governance

ESCALATE_ISSUE_TO_RISK WHEN:
  repeats_across_environments = TRUE
  OR creates_material_exposure = TRUE
  OR breaches_remediation_sla → governance_escalation
  OR linked_to { audits, policy_exceptions, regulatory_commitments }
  OR represents_systemic_control_failure across multiple domains
```

### §3.7 Risk Tier Assignment (NIST RMF Alignment)

```
# Aligned to NIST RMF organisational tiers for risk categorisation.
RISK_TIER (assign BEFORE scoring):
  Tier_1: Organisation     # enterprise-wide or cross-functional systemic risk
  Tier_2: Mission_Process  # business process, mission area, or operational domain
  Tier_3: Information_System  # specific system, platform, or application
  Tier_4: Component        # individual component, service, or interface

REQUIRED_FIELDS: { risk_tier, rationale, named_risk_owner }
CONSTRAINT: NOT assigned to Issues or Out-of-Scope items
```

---

## §4 RISK SCORING

### §4.1 Preconditions (ALL MUST be satisfied before scoring)

```
PRECONDITIONS := {
  true_risk_confirmed,              # per §3.6
  risk_tier_assigned,               # per §3.7
  stakeholders_identified: {        # Risk_Owner, Risk_Analyst, Risk_Treatment_Owner,
                                    # Control_Owner(s), Control_Operator(s)
  },
  control_effectiveness_assessed    # per §4.5, evidence-backed
}

VIOLATION: scoring_without_preconditions → NON_COMPLIANT
```

### §4.2 Inherent Risk Calculation

```
INHERENT_RISK_SCORE = IMPACT × LIKELIHOOD     # 5×5 matrix, range 1-25

RULE: Risk_Tier constrains IMPACT scope, NOT calculation
RULE: Control_Effectiveness informs LIKELIHOOD, NOT Impact
```

### §4.3 Impact Scoring (5-level)

```
IMPACT_TABLE:
  5 (Critical):  existential or near-existential (prolonged systemic outage, licence revocation,
                   critical data breach affecting >100k clients, material regulatory sanction)
  4 (High):      major disruption (significant SLA breach, regulatory enforcement action,
                   major reputational damage, material financial loss)
  3 (Moderate):  manageable disruption (localised service impact, audit finding requiring
                   remediation, moderate financial loss, contained reputational impact)
  2 (Low):       minor impact (limited operational effect, minor compliance gap,
                   low financial exposure, no client impact)
  1 (Minimal):   negligible (no measurable operational, financial, or regulatory consequence)

IMPACT_JUSTIFICATION_REQUIRED := {
  risk_tier_scope_boundary,
  business_impact_category,
  rationale_within_scope
}
```

### §4.4 Likelihood Scoring (5-level)

```
LIKELIHOOD_TABLE:
  5 (Almost Certain):  expected to occur within the assessment period; has occurred recently
  4 (Likely):          high probability; strong indicators or precedent in sector
  3 (Possible):        could occur; some enabling conditions present
  2 (Unlikely):        not expected but plausible under specific conditions
  1 (Rare):            exceptional circumstances only; no credible current threat path
```

### §4.5 Control Effectiveness (CE)

```
CE_RATINGS:
  CE-High:        effective + consistently operating  | automated, continuous monitoring, strong coverage
  CE-Medium:      present but partially effective     | mixed automation, partial coverage, gaps exist
  CE-Low:         limited reduction                   | mostly manual, retrospective, inconsistent
  CE-Unvalidated: no current evidence                 | treated as CE-Low for scoring purposes

RULE: CE-Unvalidated is the DEFAULT state until evidence is provided
RULE: CE assessment REQUIRES documented evidence (configs, logs, dashboards, audit artefacts)
```

### §4.6 CE Impact on Likelihood

```
CE_LIKELIHOOD_ADJUSTMENT:
  CE-High      → reduce likelihood 1-2 levels (justified by evidence)
  CE-Medium    → reduce likelihood 0-1 level
  CE-Low       → NO reduction
  CE-Unvalidated → NO reduction (treat as CE-Low)

WORST_CASE_RULE: if control has multiple deployments with different CE ratings,
  use the WORST CE across all deployments for scoring purposes
```

### §4.7 Residual Risk Validation Gate (MANDATORY — ALL must pass)

```
RESIDUAL_SCORING_GATE:
  □ mitigations fully implemented
  □ evidence provided (configs, logs, dashboards, audit artefacts)
  □ treatment effectiveness confirmed by Risk_Analyst
  □ governance approval documented
  □ risk_drift tracked during treatment period
  □ risk_register updated with decision and rationale

IF any □ = FALSE → residual remains at INHERENT score
```

---

## §5 TREATMENT AND ACCEPTANCE

### §5.1 Treatment Decision Types

```
TREATMENT_DECISIONS := {
  Mitigate:  reduce likelihood/impact through controls           → REQUIRES linked_controls
  Accept:    acknowledge residual within appetite                 → REQUIRES time_bound_expiry
  Transfer:  shift financial/operational impact to third party    → REQUIRES documented_rationale
  Avoid:     eliminate activity creating the risk                 → REQUIRES documented_rationale
}
```

### §5.2 Treatment Design Workflow

```
TREATMENT_DESIGN_PHASES:
  Phase_1: Assessment and Feasibility
    PARTICIPANTS: Risk_Owner, GRC_Engineer, Security_SME (for High/Critical risks)
    → identify feasible treatment options
    → validate technical viability, cost, level of effort, timeline
    → map treatments to control framework objectives
    → document residual risk posture under each option

  Phase_2: Stakeholder Commitment
    PARTICIPANTS: Risk_Owner, Treatment_Owner(s), Control_Owner(s), Control_Operator(s)
    → Treatment_Owner confirms commitment to execute
    → Control_Owner confirms control design changes required (if Mitigate)
    → Control_Operator confirms operational feasibility and resourcing
    → agree target dates, dependencies, and success criteria
    → document partial treatment rationale if not all options selected

CONSTRAINT: treatments CANNOT be presented at governance readout without:
  - GRC Engineer feasibility assessment complete
  - Treatment Owner commitment confirmed
  - Control framework mapping documented (if Mitigate decision)
  - Control Owner and Operator acknowledgement (if new or modified control required)
```

### §5.3 Treatment SLAs

```
# RECOMMENDED for regulated financial services. Align to your regulatory obligations.
TREATMENT_DECISION_SLA:
  Critical:      7 business days from identification
  High:          15 business days
  Moderate:      30 business days
  Moderate-Low:  45 business days

TREATMENT_EXECUTION_SLA:
  Critical:      30 days
  High:          90 days
  Moderate:      180 days
  Moderate-Low:  360 days
```

### §5.4 Re-evaluation Cadence (During Treatment)

```
RE_EVAL_CADENCE:
  Critical:      every 14 days
  High:          every 30 days
  Moderate:      every 60 days
  Moderate-Low:  every 90 days

CONFIRMS: { exposure_not_increased, treatment_on_track, continued_acknowledgement_appropriate }
```

### §5.5 Acceptance Rules

```
# RECOMMENDED: Aggressive acceptance limits aligned to regulated financial services expectations.
ACCEPTANCE_RULES:
  Critical:      acceptance NOT PERMITTED — must Mitigate, Transfer, or Avoid
  High:          max acceptance period 90 days, reassess every 90 days, max 1 renewal (180 days total)
                 REQUIRES: C-level or ExCo approval
  Moderate:      max acceptance period 180 days, reassess every 180 days, max 1 renewal (360 days total)
                 REQUIRES: VP+ approval
  Moderate-Low:  max acceptance period 360 days, reassess annually, max 2 renewals (3 years total)
                 REQUIRES: Director+ approval
  Low:           acceptance at Risk_Owner discretion, annual review

ACCEPTANCE_PROPERTIES:
  time_bound = TRUE                         # NEVER permanent
  suspends_sla_enforcement = FALSE
  suspends_escalation = FALSE
  suspends_monitoring = FALSE
  requires_risk_stakeholder_oversight = TRUE

EXPIRED_ACCEPTANCE:
  ACTION: flag_expired(Above_Appetite) → risk_reassessment → governance_forum_review → escalate_if_required
  STATE: remains at INHERENT_RISK level until mitigation + evidence validated
```

---

## §6 ESCALATION

### §6.1 Escalation Triggers

```
TRIGGER acceptance_governance_breach:
  condition: exceeds approved {duration, cadence, horizon}
  path:      Risk_Owner → Risk_Stakeholder → CISO → Board_Risk_Committee
  outcome:   approve_continued_acceptance OR mandate_mitigation

TRIGGER treatment_delivery_breach:
  condition: target_date missed + no revised_plan
  path:      Risk_Owner → Risk_Stakeholder → CISO
  outcome:   re-baseline plan OR executive_decision

TRIGGER sla_governance_breach:
  condition: failure to meet {treatment_decision, execution, reassessment} SLA
  path:      Risk_Analyst → Risk_Owner → Risk_Stakeholder
  outcome:   immediate_remediation + sla_restoration

TRIGGER systemic_sla_breach:
  condition: ≥2 risks breach governance_timelines in same quarter
  path:      Risk_Analyst → Governance_Body
  outcome:   root_cause + corrective_measures + executive_visibility

TRIGGER evidence_validation_failure:
  condition: controls implemented but evidence not provided within window
  path:      Risk_Analyst → Risk_Owner → Risk_Stakeholder
  outcome:   provide_evidence OR risk_stays_at_inherent + continued_sla

TRIGGER critical_risk_identified:
  condition: any risk scored Critical (20-25)
  path:      IMMEDIATE notification to CISO + Risk_Stakeholder
  outcome:   emergency treatment decision within 7 business days
```

---

## §7 MONITORING AND REPORTING

### §7.1 Executive KPIs

```
KPI above_appetite_concentration:       priority=P0, view=above-appetite risks by business_impact_category
KPI acceptance_threshold_compliance:    priority=P0, view=% within cadence + horizon limits
KPI risks_outside_agreed_dates:         priority=P0, view=count + exposure value
KPI critical_risk_count:                priority=P0, view=count of Critical-rated risks + treatment status
KPI top_concentration_risk_owners:      priority=P1, view=owners by exposure band
KPI above_appetite_exposure_aging:      priority=P1, view=duration above appetite
KPI aggregate_exposure:                 priority=P2, view=portfolio by impact_band
KPI risk_drift:                         priority=P2, view=inherent-vs-residual delta + duration
```

### §7.2 Operational Metrics

```
METRIC evidence_validation_compliance:  % mitigated risks with validated evidence pre-residual update
METRIC residual_update_integrity:       % updates only after treatment_effectiveness validation
METRIC sla_compliance:                  % meeting {treatment_decision, execution, reassessment} SLAs
METRIC control_posture_target_vs_actual: % controls implemented vs target
METRIC residual_risk_delta_posture:     gap between target posture and accepted residual
METRIC issue_remediation_rate:          % of issues remediated within SLA by severity
```

### §7.3 Governance Enforcement Rules (NON-DISCRETIONARY)

```
RULE MON-1: residual_risk MUST_NOT update until mitigation complete + validated (§4.7)
RULE MON-2: risks under mitigation remain "Acknowledged at Inherent Risk"
RULE MON-3: risk_drift MUST be tracked and reported
RULE MON-4: SLA/acceptance/cadence breaches → ESCALATE (§6)
RULE MON-5: expired acceptances → governance_breach → executive_review
RULE MON-6: Critical risks → standing agenda item at every governance forum until resolved
```

### §7.4 Governance Forum

```
# [CUSTOMISE] Frequency and attendees to match your governance calendar.
FORUM:
  frequency: monthly (RECOMMENDED); fortnightly for Critical risk periods
  mandatory_attendees: Risk_Owners + Treatment_Owners (for approaching/breached SLAs)
  standing: Risk_Analysts (facilitators), GRC_Engineer, CISO
  escalation: Risk_Stakeholders as required

AGENDA := [
  critical_risk_review,
  accepted_risk_review,
  risk_drift_review,
  risks_outside_agreed_dates,
  evidence_validation_check,
  issue_escalation_review,
  executive_kpi_review,
  escalation_determination
]
```

---

# PART 2: CONTROL MANAGEMENT

## §8 CONTROL OBJECT MODEL

### §8.1 Hierarchy

```
CONTROL_HIERARCHY:
  Level_1: Control_Objective  ("what we achieve" — measurable security outcome)
    └── Level_2: Control_Activity  ("what we do to achieve it" — specific procedure)
          └── Level_3: Control_Deployment  (activity × asset — "where we do it")

RULES:
  RULE CH-1: every Control_Activity MUST have exactly one parent Control_Objective
  RULE CH-2: every Control_Objective MUST belong to exactly one Control_Family
  RULE CH-3: every Control_Deployment MUST reference one Control_Activity and one Asset
  RULE CH-4: a Control_Objective MAY have zero Control_Activities (scaffolded, not yet decomposed)
  RULE CH-5: a Control_Activity MAY be deployed to 1..N Assets (1:many)
  RULE CH-6: deleting a Control_Objective is BLOCKED if it has linked risks or active deployments
```

### §8.2 Control Object Fields

#### Control_Objective (Level 1)

```
CONTROL_OBJECTIVE := {
  id:                 string,
  title:              string,
  control_family:     enum(Control_Family),
  description:        string,
  control_type:       enum(Automated, Manual, Partially_Automated),
  classification:     enum(Direct, Indirect, Compliance),
  frequency:          enum(Continuous, Weekly, Monthly, Quarterly, Annually),
  kpi:                string,
  sla:                string,
  compliance_mappings: list[enum(...)],
  lifecycle_status:   enum(see §9.1),
  control_owner:      user_ref,
  control_operator:   user_ref,
  linked_policies:    list[policy_id],
  linked_risks:       list[risk_id],
  created_at:         datetime,
  updated_at:         datetime
}
```

#### Control_Activity (Level 2)

```
CONTROL_ACTIVITY := {
  id:                   string,
  parent_objective_id:  objective_id,
  title:                string,
  description:          string,
  category:             enum(Control_Activity, Documentation, Framework),
  compliance_scope:     list[enum(...)],
  compliance_ref:       string,
  lifecycle_status:     enum(see §9.2),
  assigned_operator:    user_ref,
  priority:             enum(P0, P1, P2, P3),
  created_at:           datetime,
  updated_at:           datetime
}
```

#### Control_Deployment (Level 3 — join object)

```
CONTROL_DEPLOYMENT := {
  id:                    uuid,
  control_activity_id:   activity_id,
  asset_id:              asset_id,       # FK → Asset Register / CMDB
  deployment_status:     enum(see §9.3),
  ce_rating:             enum(CE-High, CE-Medium, CE-Low, CE-Unvalidated),
  ce_last_assessed:      date,
  ce_assessed_by:        user_ref,
  ce_evidence_ref:       string,
  last_test_date:        date,
  next_test_due:         date,
  test_result:           enum(Pass, Fail, Partial, Not_Tested),
  test_performed_by:     user_ref,
  created_at:            datetime,
  updated_at:            datetime
}
```

### §8.3 Control Families

```
# [CUSTOMISE] Align to your control framework. RECOMMENDED baseline (16 families):
CONTROL_FAMILIES := {
  Asset_Management, Business_Continuity, Change_Management,
  Application_Security, Communications_Security, Configuration_Management,
  Data_Management, Identity_and_Access_Management, Incident_Response,
  Network_Operations, Risk_Management, Security_Awareness_and_Training,
  Security_Governance, Third_Party_and_Supplier_Risk,
  Systems_Monitoring_and_Detection, Vulnerability_Management
}
```

---

## §9 CONTROL LIFECYCLE STATES

### §9.1 Control_Objective Lifecycle

```
OBJECTIVE_STATES:
  Design, Implementation, Operating, Failure, Redesign, Deprecated

VALID_TRANSITIONS:
  Design          → Implementation  (when ≥1 activity defined + deployment plan exists)
  Implementation  → Operating       (when all target deployments active + first CE assessed)
  Operating       → Failure         (when CE-Low on critical deployment OR test result = Fail)
  Failure         → Redesign        (when remediation requires architectural change)
  Failure         → Operating       (when remediated + CE re-assessed)
  Redesign        → Implementation  (when redesigned and ready for re-deployment)
  Operating       → Deprecated      (governance-approved retirement)

BLOCKING RULES:
  RULE OL-1: CE fields ONLY editable when status = Operating
  RULE OL-2: test scheduling ONLY active when status = Operating
  RULE OL-3: Deprecated BLOCKED if linked risks ≠ { Closed, Accepted, Transferred }
  RULE OL-4: Operating REQUIRES ≥1 Control_Deployment in active state
  RULE OL-5: Failure TRIGGERS warning banner on ALL linked risk records
```

### §9.2 Control_Activity Lifecycle

```
ACTIVITY_STATES: Draft, Active, Suspended, Retired

RULE AL-1: Retiring with active deployments REQUIRES all deployments Decommissioned first
RULE AL-2: Draft activities CANNOT be linked to risk records
```

### §9.3 Control_Deployment Lifecycle

```
DEPLOYMENT_STATES: Planned, Active, Degraded, Failed, Decommissioned

RULE DL-1: Failed → trigger Failure propagation check on parent Objective
RULE DL-2: CE ONLY editable when status = Active OR Degraded
RULE DL-3: Decommissioned deployments are READ-ONLY
```

---

## §10 CONTROL TESTING

### §10.1 Testing Cadence

```
TEST_CADENCE:
  Continuous controls:  test every 3 months (RECOMMENDED)
  Monthly controls:     test every 6 months
  Quarterly controls:   test every 12 months
  Annual controls:      test every 24 months

RULE TST-1: test results are IMMUTABLE; corrections create new records
RULE TST-2: test failure triggers CE re-assessment
RULE TST-3: overdue test (> cadence + 30 days) auto-downgrades CE to CE-Unvalidated
```

### §10.2 CE Expiry

```
CE_EXPIRY:
  Continuous: 2 months | Monthly: 6 months | Quarterly: 12 months | Annual: 24 months
EXPIRED_CE → auto-downgrade to CE-Unvalidated; no manual override
```

---

## §11 INTER-MODULE RELATIONSHIPS: CONTROLS

### §11.1 Controls ↔ Risk Register

```
RELATIONSHIP risk_controls:
  type:   M:M (many risks ↔ many control_objectives)
  join:   risk_controls { risk_id, control_id, ce_at_assessment, assessed_date }

  RULE RCR-1: CE at assessment is SNAPSHOTTED into the join record
  RULE RCR-2: subsequent CE changes FLAG risk for re-evaluation but do NOT auto-update
  RULE RCR-3: worst-case CE across all deployments informs likelihood (per §4.6)
  RULE RCR-4: Control in Failure state → warning on ALL linked risk records
  RULE RCR-5: Design/Implementation controls CANNOT be used as CE evidence
```

### §11.2 CE Change → Risk Re-evaluation Trigger

```
TRIGGER ce_change_impact:
  WHEN: ce_rating changes on any deployment linked to a risk
  IF degradation:
    flag risk "Control_Changed — Re-evaluation Required"
    re-evaluation within: Critical: 5bd | High: 10bd | Moderate: 20bd | Mod-Low: 30bd
  IF improvement AND residual_score_locked:
    flag risk "Control_Improved — Residual Update Eligible"
    full validation gate (§4.7) still required
```

### §11.3 Controls ↔ Issues

```
RELATIONSHIP control_issues:
  type:   1:N (one control_deployment → many issues)
  RULE CI-1: test result = Fail → auto-create Issue linked to deployment
  RULE CI-2: issue remediation → triggers CE re-assessment on linked deployment
  RULE CI-3: issue breaching SLA → evaluate for risk register promotion (per §3.6)
```

---

# PART 3: POLICY GOVERNANCE

## §12 POLICY HIERARCHY

### §12.1 Structure

```
POLICY_HIERARCHY:
  Level_1: Policy         "the WHY and WHAT — organisational governance commitment"
    └── Level_2: Standard  "the HOW — technical and procedural implementation requirements"
          └── Level_3: Control_Objective  "the WHAT WE ACHIEVE — measurable outcome"
                └── Level_4: Control_Activity  "the WHAT WE DO — specific procedures"

HIERARCHY_RULES:
  RULE PH-1: Policy MUST have ≥1 linked Control_Objective (or governance_gap)
  RULE PH-2: Standard MUST link to exactly one parent Policy
  RULE PH-3: Control_Objective MAY map to multiple Policies and Standards (M:M)
  RULE PH-4: Policy MUST be owned by named Policy_Owner (≥ Director)
  RULE PH-5: orphaned Standards → governance_gap → assign within 30 days
```

### §12.2 Policy Object Fields

```
POLICY := {
  id, title, version (semver), status (see §13.1),
  policy_type: enum(Security, Privacy, Operational, Compliance, Governance),
  policy_owner, policy_approver (CISO+),
  effective_date, next_review_date, review_cycle: enum(Annual, Biennial),
  scope, compliance_mappings, linked_standards, linked_controls, linked_risks,
  exception_count, version_history
}
```

### §12.3 Policy Exception Fields

```
POLICY_EXCEPTION := {
  id, policy_id (FK), title, requestor,
  business_justification, risk_statement,
  compensating_controls: list[objective_id],
  status: enum(Requested, Approved, Rejected, Expired),
  approved_by, effective_date, expiry_date (MANDATORY),
  rmf_promoted: boolean, rmf_risk_id (FK if promoted)
}

EXCEPTION_RULES:
  RULE PE-1: ALWAYS time-bound (max 1yr; CISO approval for 2yr)
  RULE PE-2: without compensating controls → auto-escalate for risk promotion
  RULE PE-3: systemic/prolonged → MUST promote to risk register
  RULE PE-4: expiry within 30d → notify Policy_Owner + requestor
  RULE PE-5: expired without renewal → governance_gap; notify CISO
```

---

## §13 POLICY LIFECYCLE STATES

### §13.1 Policy Lifecycle

```
POLICY_STATES: Draft, Under_Review, Approved, Active, Under_Revision, Deprecated

BLOCKING RULES:
  RULE PL-1: Active REQUIRES { approver signed off, effective_date, ≥1 linked control }
  RULE PL-2: Deprecated BLOCKED if linked risks ≥ Moderate
  RULE PL-3: Under_Revision remains enforceable
  RULE PL-4: new version REQUIRES increment + change_summary

REVIEW TRIGGERS: regulatory change, incident, audit finding, >5 exceptions, linked risk → Critical/High
```

---

## §14 POLICY RELATIONSHIPS

```
RULE PC-1: policy revision → control re-alignment check within 30 days
RULE PC-2: policy deprecation → control_objectives re-mapping within 60 days
RULE PC-3: unmapped control_objectives → governance_gap; report monthly
RULE PR-1: policy failure → linked risk records must reflect
RULE PR-2: exception promoted to risk → bidirectional linkage maintained
```

---

## §15 COMPLIANCE FRAMEWORK MAPPING

```
COMPLIANCE_FRAMEWORKS := [CUSTOMISE: e.g. { SOC2, ISO27001, FedRAMP, HIPAA, DORA, PCI_DSS }]

RULE CF-1: policies/standards MUST declare compliance frameworks
RULE CF-2: control_objectives inherit mappings from linked policies/standards
RULE CF-3: coverage gaps → governance_gaps in dashboard
RULE CF-4: annual-audit frameworks MUST have Annual review cycle
```

---

# PART 4: INVARIANTS (HARD RULES — NEVER VIOLATED)

## §16 Risk Management Invariants

```
INVARIANT RINV-1:  residual_risk NEVER updated without validated evidence
INVARIANT RINV-2:  risk_appetite NEVER downgraded without formal governance
INVARIANT RINV-3:  control_owners NEVER assigned as risk_owners
INVARIANT RINV-4:  acceptance NEVER permanent — always time-bound
INVARIANT RINV-5:  Critical risks NEVER accepted — must Mitigate, Transfer, or Avoid
INVARIANT RINV-6:  risk_readout NEVER skipped for risks rated Moderate or above
INVARIANT RINV-7:  issues NEVER scored as risks without promotion criteria met
INVARIANT RINV-8:  scoring NEVER begins without preconditions (§4.1) satisfied
INVARIANT RINV-9:  planned/partial/unvalidated controls NEVER reduce residual risk
INVARIANT RINV-10: every risk MUST have Risk_Owner AND Risk_Stakeholder
INVARIANT RINV-11: expired risks ALWAYS escalated — no silent expiry
INVARIANT RINV-12: treatments NEVER presented at readout without GRC Engineer validation + treatment owner commitment
INVARIANT RINV-13: partial treatment selection ALWAYS documented with rationale
```

## §17 Control Management Invariants

```
INVARIANT CINV-1:  CE evidence REQUIRED for any rating other than CE-Unvalidated
INVARIANT CINV-2:  Design/Implementation controls NEVER used as CE evidence
INVARIANT CINV-3:  Control_Owner NEVER assigned as Risk_Owner for linked risks
INVARIANT CINV-4:  CE assessment NEVER on Decommissioned deployments
INVARIANT CINV-5:  Failure state ALWAYS propagates warning to linked risks
INVARIANT CINV-6:  worst-case CE ALWAYS used in scoring (never best-case)
INVARIANT CINV-7:  test history IMMUTABLE; no edits, only superseding records
INVARIANT CINV-8:  control retirement BLOCKED if linked risks above-appetite and unmitigated
INVARIANT CINV-9:  asset decommission NEVER silently removes risk-control linkages
INVARIANT CINV-10: CE expiry auto-downgrades to CE-Unvalidated; no override
```

## §18 Policy Management Invariants

```
INVARIANT PINV-1:  Active policy MUST have ≥1 linked control_objective
INVARIANT PINV-2:  policy exceptions NEVER permanent — always time-bound
INVARIANT PINV-3:  deprecation NEVER silently removes risk-policy linkages
INVARIANT PINV-4:  compliance-mapped policies MUST have Annual review — no exceptions
INVARIANT PINV-5:  approval REQUIRES CISO+ — no self-approval by Policy_Owner
INVARIANT PINV-6:  Under_Revision policies remain enforceable
INVARIANT PINV-7:  standard revision ALWAYS triggers control alignment check
INVARIANT PINV-8:  retirement BLOCKED if linked risks Critical/High and unmitigated
INVARIANT PINV-9:  version history IMMUTABLE — always retained for audit
```

---

# PART 5: THREAT MANAGEMENT

## §19 THREAT MODEL LIFECYCLE

### §19.1 Structure and Applicability

```
THREAT_MODEL_SCOPE := all { new_features_with_material_impact, architectural_changes, critical_systems }

THREAT_SCENARIO := {
  category: enum(STRIDE - Spoofing, Tampering, Repudiation, Information_Disclosure, Denial_of_Service, Elevation_of_Privilege),
  inherent_severity: enum(Critical, High, Medium, Low),
  status: enum(Identified, Mitigated, Accepted, Promoted_To_Risk)
}
```

### §19.2 Lifecycle Phases

```
THREAT_MODEL_STATES: Scope, Decomposition, Threat_Analysis, Mitigation_Design, Review, Active, Deprecated

VALID_TRANSITIONS:
  Scope             → Decomposition      (REQUIRES ≥1 linked asset / attack_surface)
  Decomposition     → Threat_Analysis    (REQUIRES ≥1 trust boundary or component)
  Threat_Analysis   → Mitigation_Design  (when ≥1 threat scenario is defined)
  Mitigation_Design → Review             (all critical/high threats mitigated or decisioned)
  Review            → Active             (AppSec + System_Owner sign-off)
```

### §19.3 Invariants & Validation Gates

```
INVARIANT TINV-1: Threat Scenario MUST have at least one assigned mitigation OR be accepted locally (Low only) OR promoted to Risk Register (Medium+).
INVARIANT TINV-2: Threat Model CANNOT proceed from Review to Active without AppSec and System_Owner sign-off.
INVARIANT TINV-3: Medium, High, or Critical threat scenarios CANNOT be "Accepted" without promotion to the formal GRC risk register.
INVARIANT TINV-4: Full Mitigation of a threat scenario REQUIRES an active, linked control_deployment. 
INVARIANT TINV-5: Low severity threat scenario accepted locally MUST carry a time-bound acceptance_expiry (max 12 months). Re-evaluation required on expiry. Equivalent to RINV-4 for risk-layer acceptance.
RULE TM-PARTIAL: threat_scenario.status CANNOT be set to Mitigated if any threat_mitigation_links row for that scenario carries effectiveness_assurance = Partially_Mitigated. Scenario remains Identified. A distinct UI state "Partially Mitigated" may be derived for display purposes from the link table but is not a database status value.

VIOLATION(TINV-*) → Blocks state transition.
```

## §20 THREAT CASCADE ENGINE

### §20.1 Promotion to Risk Register

```
PROMOTE_THREAT_TO_RISK WHEN:
  inherent_severity IN (Medium, High, Critical) AND mitigation is infeasible
  OR status = Identified AND remediation_timeline exceeds 30 days without interim mitigation

POST_PROMOTE: 
  create_risk_record + assign_risk_owner(system_owner) 
  bidirectional_link created between threat_scenario and risk
```

### §20.2 Control Failure Cascade

```
TRIGGER tm_control_failure:
  WHEN: control_deployment linked via threat_mitigation_links transitions to Failure
  IF threat_scenario was previously Mitigated:
    threat_scenario.status = Identified
    threat_model.lifecycle_state = Review (reopened)
    notify(System_Owner, AppSec, Risk_Owner of any linked promoted risk)
    IF duration > 15bd → PROMOTE_THREAT_TO_RISK
```

§20.3 MITIGATION SUCCESS CASCADE
TRIGGER: threat_scenario.status transitions to Mitigated (all links Fully_Mitigated, TINV-4 satisfied)
IF threat_scenario.promoted_risk_id IS NOT NULL:
    linked risk record flagged "Linked Threat Mitigated — Re-evaluation Eligible"
    Risk_Owner notified
    Risk_Analyst notified
    Risk residual score NOT automatically updated — full gate (RINV-1) still required

```
---

# APPENDICES

## Appendix A: Scoring Matrix (5x5)
```

              Impact →    1(Minimal) 2(Low)   3(Mod)   4(High)  5(Critical)
Likelihood ↓
5 (Almost Certain)          5         10       15       20       25
4 (Likely)                  4          8       12       16       20
3 (Possible)                3          6        9       12       15
2 (Unlikely)                2          4        6        8       10
1 (Rare)                    1          2        3        4        5

RATING BANDS:
  1-4:   Low           (Within Appetite)
  5-9:   Moderate-Low  (At Appetite)
  10-14: Moderate      (Above Appetite)
  15-19: High          (Above Appetite)
  20-25: Critical      (Above Appetite)

```

## Appendix B: SLA Quick Reference (Banking-Aligned)
```

TREATMENT DECISION SLA:       Critical: 7bd | High: 15bd | Moderate: 30bd | Mod-Low: 45bd
TREATMENT EXECUTION SLA:      Critical: 30d | High: 90d | Moderate: 180d | Mod-Low: 360d
RE-EVALUATION CADENCE:        Critical: 14d | High: 30d | Moderate: 60d | Mod-Low: 90d
ACCEPTANCE LIMITS:
  Critical: NOT PERMITTED
  High:     90d, max 1 renewal (180d total), C-level approval
  Moderate: 180d, max 1 renewal (360d total), VP+ approval
  Mod-Low:  360d, max 2 renewals (3yr total), Director+ approval
  Low:      Risk_Owner discretion, annual review
RISK OWNER ASSIGNMENT:        Critical: 3bd | All others: 5bd
CE RE-EVALUATION (degradation): Critical: 5bd | High: 10bd | Moderate: 20bd | Mod-Low: 30bd
ISSUE REMEDIATION SLA:        Critical: 5bd | High: 15bd | Moderate: 30bd | Mod-Low: 60bd | Low: 90bd

```

## Appendix C: Entity Relationship Summary
```

Policy ──────────────── 1:N ──── Standard
Policy ──────────────── M:M ──── Control_Objective
Policy ──────────────── M:M ──── Risk
Policy ──────────────── 1:N ──── Policy_Exception

Standard ────────────── M:M ──── Control_Objective
Standard ────────────── M:M ──── Control_Activity

Control_Objective ───── 1:N ──── Control_Activity
Control_Activity ────── 1:N ──── Control_Deployment
Control_Deployment ──── N:1 ──── Asset (via CMDB integration)
Control_Deployment ──── 1:N ──── Issue

Control_Objective ───── M:M ──── Risk (via risk_controls join)
Control_Objective ───── M:M ──── Treatment (via control mapping)

Policy_Exception ────── conditional ──── Risk (via promotion)

Threat_Model ────────── 1:N ──── Threat_Component
Threat_Component ────── 1:N ──── Threat_Scenario
Threat_Scenario ─────── M:M ──── Control_Deployment (via threat_mitigation_links)
Threat_Scenario ─────── conditional ──── Risk (via promotion)

```

## Appendix D: Lifecycle State Machines
```

RISK:        [Intake] → [Preconditions] → [Scoring] → [Treatment] → [Readout] → [Evidence+Residual] → [Monitoring]

OBJECTIVE:   [Design] → [Implementation] → [Operating] ⇄ [Failure] ⇄ [Redesign] → [Deprecated]

ACTIVITY:    [Draft] → [Active] ⇄ [Suspended] → [Retired]

DEPLOYMENT:  [Planned] → [Active] ⇄ [Degraded] ⇄ [Failed] → [Decommissioned]

POLICY:      [Draft] → [Under_Review] ⇄ [Approved] → [Active] ⇄ [Under_Revision] → [Deprecated]

EXCEPTION:   [Requested] → [Approved] → [Expired]
                         ↘ [Rejected]

THREAT_MODEL:[Scope] → [Decomposition] → [Threat_Analysis] → [Mitigation_Design] ⇄ [Review] ⇄ [Active] → [Deprecated]
                                                                                   ↓
                                                                              [Abandoned]*
*(Any state except Active can transition to Abandoned)

```

## Appendix E: NIST RMF Tier Alignment
```

  Tier 1 (Organisation):     enterprise-wide, cross-functional, systemic
  Tier 2 (Mission/Process):  business process, mission area, operational domain
  Tier 3 (Information System): specific system, platform, or application
  Tier 4 (Component):        individual component, service, interface

```

---

*This specification template is released under CC BY 4.0. Adapt freely with attribution.*
