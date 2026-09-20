# Data Model

**Version:** 1.4 | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](../specification/codified-rules.md) and validated against the [reference implementation](../platform).
**Purpose:** Complete relational schema for the governance platform. 49 tables across 8 domains. All FK relationships, named constraints, and schema-level invariant enforcement documented. Designed for implementation teams to reproduce the data layer with full traceability to the specification.

> **Design principle:** The schema is the first line of enforcement. Every NOT NULL, CHECK, UNIQUE, and FK constraint exists because a codified rule requires it. If a constraint is absent, the rule is not enforced at the data layer and must be enforced at the service layer. See [Invariants Catalogue](../specification/invariants-catalogue.md) for the complete enforcement mapping.

> **Implementation note:** PostgreSQL. All tables use `uuid` primary keys,
> timestamps are `timestamptz` defaulting to `now()`, and the schema is created
> and versioned by Alembic.
>
> **On where enforcement lives.** An earlier revision of this document said row
> level security was enforced on every table. The [reference
> implementation](../platform) uses none: immutability is enforced by database
> trigger on the six append-only tables, hard rules by `CHECK` and `NOT NULL`
> constraints, and authorisation at the service layer, where the state machine
> can name the rule that refused. That distinction is the whole subject of the
> [Invariants Catalogue](../specification/invariants-catalogue.md), so this
> document should not have described a mechanism the implementation does not
> use. RLS remains a reasonable choice for a deployment that wants it, and the
> schema does not prevent it.

---

## Table of Contents

1. [Schema Overview](#1-schema-overview)
2. [Domain 1: Platform and Identity](#2-domain-1-platform-and-identity)
3. [Domain 2: Risk Management](#3-domain-2-risk-management)
4. [Domain 3: Control Management](#4-domain-3-control-management)
5. [Domain 4: Treatment Management](#5-domain-4-treatment-management)
6. [Domain 5: Policy and Standards](#6-domain-5-policy-and-standards)
7. [Domain 6: Vendor and Third-Party Risk](#7-domain-6-vendor-and-third-party-risk)
8. [Domain 7: Threat Management](#8-domain-7-threat-management)
9. [Domain 8: Compliance and Assurance](#9-domain-8-compliance-and-assurance)
10. [Foreign Key Relationship Map](#10-foreign-key-relationship-map)
11. [Schema-Level Constraint Summary](#11-schema-level-constraint-summary)
12. [Invariant Enforcement at Schema Layer](#12-invariant-enforcement-at-schema-layer)

---

## 1. Schema Overview

| Domain | Tables | Purpose |
|---|---|---|
| Platform and Identity | 7 | User profiles, roles, groups, audit logging, notifications, OIDC role mapping |
| Risk Management | 8 | Risk register, 7-phase lifecycle, phase history, comments, attachments, reviews, control links, treatment links, policy links |
| Control Management | 5 | Three-level control hierarchy (objective, activity, deployment), immutable test history, asset register |
| Treatment Management | 3 | Treatment plans, approval workflows, progress check-ins |
| Policy and Standards | 7 | Policy register, standards, versions, exceptions, control links, AI assessments, AI recommendations |
| Vendor and Third-Party Risk | 8 | Vendor register, engagements (assessment lifecycle), inherent risk assessments, due diligence artefacts, findings, approval decisions, offboarding, analyst tasks |
| Compliance and Assurance | 4 | Framework register, requirement catalogue, Statement of Applicability positions, control-to-requirement coverage assertions |
| Threat Management | 7 | Threat models, components (DFD items with classification and trust zone), STRIDE threat scenarios, mitigation links to deployed controls, scenario comments, append-only evidence, risk register links |
| **Total** | **49** | |

> **Scope note.** This is the framework's reference data model. The [reference implementation](../platform) builds 34 of these tables: it covers identity, risk, control, treatment, policy and threat management, and does not yet implement the vendor and third-party risk domain, the policy AI assessment tables, or the group and OIDC role-mapping tables. Where the two differ, this document describes the target and the platform's own schema is the subset currently enforced.

### Entity Relationship Summary

```
profiles ←── user_roles
         ←── user_groups ←── user_group_members
         ←── role_mappings (OIDC)

risks ←── risk_phase_history
      ←── risk_comments (threaded)
      ←── risk_attachments
      ←── risk_reviews
      ←── risk_assets ──→ attack_surfaces
      ←── risk_controls ──→ control_objectives
      ←── risk_treatments ──→ treatments
      ←── risk_policy_links ──→ policies

control_objectives ←── control_activities ←── control_deployments ──→ attack_surfaces
                                               ←── control_tests (append-only)
                   ←── control_requirement_links ──→ compliance_requirements
                   ←── policy_controls ──→ policies
                   ←── risk_controls ──→ risks

treatments ←── treatment_approvals
           ←── treatment_checkins
           ←── risk_treatments ──→ risks

policies ←── standards
         ←── policy_versions
         ←── policy_exceptions
         ←── policy_controls ──→ control_objectives
         ←── policy_ai_assessments ←── policy_ai_recommendations
         ←── risk_policy_links ──→ risks

vendors ←── engagements ←── ira_assessments
                        ←── dd_artefacts
                        ←── dd_findings
                        ←── approval_decisions
                        ←── offboarding_checklist
                        ←── analyst_tasks
        ←── analyst_tasks (direct)

threat_models ←── threat_components ←── threat_scenarios ──→ risks (promoted_risk_id)
              ←── threat_scenarios ←── threat_mitigation_links ──→ control_deployments
                                   ←── threat_scenario_comments (threaded)
                                   ←── threat_scenario_evidence (append-only)
                                   ←── threat_scenario_risk_links ──→ risks

compliance_frameworks ←── compliance_requirements ←── requirement_assessments
                                                    ←── control_requirement_links ──→ control_objectives
attack_surfaces.compliance_scopes ──→ compliance_frameworks (by framework_id)

engagements ──→ risks (promoted_risk_id: promoted vendor findings)
```

---

## 2. Domain 1: Platform and Identity

### profiles

User identity records. Synced from auth provider. Supports deactivation without deletion for audit trail preservation.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | (from auth) | PK. References auth.users(id). |
| full_name | text | YES | | Display name |
| email | text | YES | | |
| avatar_url | text | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |
| deactivated_at | timestamptz | YES | | Soft delete. Preserves audit references. |

### user_roles

RBAC role assignments. One user can hold multiple roles.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | | FK to auth.users |
| role | app_role (enum) | NO | | Platform role |
| created_at | timestamptz | NO | now() | |

**Constraints:** UNIQUE on (user_id, role). Prevents duplicate role assignment.

### user_groups

Organisational groupings for notification routing and ownership assignment.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO | | UNIQUE |
| description | text | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### user_group_members

Junction table: users to groups.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| group_id | uuid | NO | | FK to user_groups |
| user_id | uuid | NO | | FK to auth.users |
| added_by | uuid | YES | | |
| added_at | timestamptz | YES | now() | |

**Constraints:** UNIQUE on (group_id, user_id).

### role_mappings

OIDC group-to-platform-role mapping. Enables SSO integration (Okta, Azure AD, etc.).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| okta_group | text | NO | | OIDC group claim value |
| app_role | text | NO | | Maps to app_role enum |
| created_at | timestamptz | NO | now() | |
| created_by | uuid | YES | | |

### audit_log

Immutable event log. No UPDATE or DELETE permitted.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | YES | | Who performed the action |
| entity_type | text | NO | | Table/domain name |
| entity_id | uuid | YES | | Record affected |
| action | text | NO | | CREATE, UPDATE, DELETE, PHASE_ADVANCE, etc. |
| changed_fields | jsonb | YES | | Before/after values for UPDATE |
| created_at | timestamptz | NO | now() | |

### in_app_notifications

User-facing notification queue. Driven by cascade events, SLA breaches, and workflow triggers.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| recipient_id | uuid | NO | | FK to auth.users |
| entity_type | text | YES | | Source entity type |
| entity_id | uuid | YES | | Source record |
| event_type | text | NO | | Notification category |
| title | text | NO | | |
| body | text | YES | | |
| is_read | boolean | NO | false | |
| created_at | timestamptz | NO | now() | |

---

## 3. Domain 2: Risk Management

### risks

Core risk register. 7-phase lifecycle with phase-gated transitions enforced at service layer.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | text | NO | | Human-readable ID (RISK-001). UNIQUE. |
| title | text | NO | | |
| phase | integer | NO | 1 | 1-7. CHECK constraint. |
| lifecycle_state | text | NO | 'Intake' | CHECK constraint on valid states. |
| cause | text | YES | | Structured risk statement |
| threat_event | text | YES | | Structured risk statement |
| vulnerability | text | YES | | Structured risk statement |
| impact_statement | text | YES | | Structured risk statement |
| intake_source | text | YES | | CHECK constraint on valid sources |
| risk_level | text | YES | | CHECK constraint |
| tier | text | YES | | NIST RMF Tier 1-4. CHECK constraint. |
| impact | integer | YES | | 1-5. CHECK constraint. |
| likelihood | integer | YES | | 1-5. CHECK constraint. |
| inherent_risk_score | integer | YES | | Computed: impact x likelihood |
| inherent_rating | text | YES | | CHECK constraint on rating bands |
| ce_rating | text | YES | | CHECK constraint on CE values |
| residual_impact | integer | YES | | 1-5. CHECK constraint. |
| residual_likelihood | integer | YES | | 1-5. CHECK constraint. |
| residual_risk_score | integer | YES | | Computed: residual_impact x residual_likelihood |
| residual_rating | text | YES | | CHECK constraint on rating bands |
| treatment_strategy | text | YES | | Accept/Mitigate/Transfer/Avoid. CHECK. |
| acceptance_expiry_date | date | YES | | RINV-4: NOT NULL when strategy=Accept |
| acceptance_reassessment_count | integer | NO | 0 | |
| next_review_date | date | YES | | |
| sla_status | text | NO | 'On_Track' | CHECK constraint |
| escalation_flag | boolean | NO | false | |
| pre_true_risk_confirmed | boolean | NO | false | **RINV-8.1**, and the only stored Phase 2 condition. Triage deciding that an item is a risk rather than an issue is a judgement the record cannot supply |
| gate_mitigations_implemented | boolean | NO | false | Phase 6 gate |
| gate_evidence_provided | boolean | NO | false | Phase 6 gate |
| gate_effectiveness_confirmed | boolean | NO | false | Phase 6 gate |
| gate_governance_approved | boolean | NO | false | Phase 6 gate |
| gate_drift_tracked | boolean | NO | false | Phase 6 gate |
| readout_confirmed | boolean | NO | false | Phase 5 gate |
| readout_conducted_at | timestamptz | YES | | |
| readout_adjustment_rationale | text | YES | | |
| secarch_validated | boolean | NO | false | GRC Engineer validation (RINV-12) |
| expected_residual_impact | integer | YES | | 1-5. CHECK. Pre-treatment estimate. |
| expected_residual_likelihood | integer | YES | | 1-5. CHECK. |
| expected_residual_score | integer | YES | | |
| treatment_delivery_horizon | date | YES | | |
| required_evidence_list | text | YES | | |
| transfer_description | text | YES | | |
| avoidance_description | text | YES | | |
| residual_impact_rationale | text | YES | | |
| residual_likelihood_rationale | text | YES | | |
| residual_gate_notes | jsonb | YES | '{}' | |
| closure_rationale | text | YES | | |
| closed_at | timestamptz | YES | | |
| closed_by | uuid | YES | | |
| impact_justification | text | YES | | |
| ce_evidence_reference | text | YES | | |
| likelihood_justification_threat | text | YES | | |
| likelihood_justification_exposure | text | YES | | |
| likelihood_justification_historical | text | YES | | |
| likelihood_justification_controls | text | YES | | |
| precondition_notes | jsonb | YES | '{}' | |
| risk_owner_id | uuid | YES | | RINV-10 requires NOT NULL (service enforcement) |
| risk_stakeholder_id | uuid | YES | | RINV-10 requires NOT NULL (service enforcement) |
| risk_analyst_id | uuid | YES | | |
| identified_by | text | YES | | |
| rationale_intake | text | YES | | |
| materiality_bc | boolean | NO | false | Business continuity materiality |
| materiality_ipo | boolean | NO | false | IPO materiality |
| materiality_audit | boolean | NO | false | Audit materiality |
| attack_surface_ids | jsonb | NO | '[]' | Linked asset IDs |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Named CHECK constraints:** phase (1-7), lifecycle_state, intake_source, risk_level, tier, impact (1-5), likelihood (1-5), inherent_rating, ce_rating, residual_impact (1-5), residual_likelihood (1-5), residual_rating, treatment_strategy, sla_status, expected_residual_impact (1-5), expected_residual_likelihood (1-5).

> **The other three Phase 2 conditions are columns no longer.** `tier_assigned`,
> `stakeholders_identified` and `control_effectiveness_assessed` were stored
> booleans, so RINV-8's "all four must hold" was satisfied by ticking four
> boxes. They are computed from the record: the tier and its rationale, the
> three named roles, and a linked control the scoring engine would actually
> count. See [codified-rules §4.1](../specification/codified-rules.md).

### risk_phase_history

Immutable phase transition audit trail.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| from_phase | integer | YES | | NULL for initial creation |
| to_phase | integer | NO | | |
| changed_by | uuid | YES | | |
| changed_fields | jsonb | YES | | Snapshot of fields at transition |
| created_at | timestamptz | NO | now() | |

### risk_comments

Threaded discussion on risk records. Self-referencing FK for replies.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| parent_comment_id | uuid | YES | | FK to risk_comments (self-ref) |
| body | text | NO | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### risk_attachments

Evidence files linked to risk records.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| filename | text | NO | | |
| file_path | text | NO | | S3 or local path |
| uploaded_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |

### risk_reviews

Periodic review records. Tracks who reviewed and when next review is due.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| reviewed_by | uuid | YES | | |
| review_notes | text | NO | | |
| next_review_date | date | YES | | |
| created_at | timestamptz | NO | now() | |

### risk_assets

Junction: risks to the assets they concern. Declares the scope a control has to
be deployed inside before it reduces this risk (RINV-14).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| attack_surface_id | uuid | NO | | FK to attack_surfaces |
| linked_at | timestamptz | NO | now() | |
| linked_by | uuid | YES | | |

**Constraints:** UNIQUE on (risk_id, attack_surface_id).

**On the absent row.** A risk with no row here has an *undeclared* scope, not an
empty one, and the CE filter does not run. Zero is a legitimate answer for an
organisational risk that concerns no single system, so this cannot be modelled
as a mandatory column on `risks` without making the field a lie on every such
record. The distinction is surfaced in the interface rather than inferred,
because an empty exclusion list means nothing on its own.

### risk_controls

Junction: risks to controls. Captures CE rating at time of assessment (snapshot).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| control_id | uuid | NO | | FK to controls |
| ce_rating_at_assessment | text | YES | | CE snapshot at link time |
| linked_at | timestamptz | NO | now() | |
| linked_by | uuid | YES | | |

**Constraints:** UNIQUE on (risk_id, control_id).

### risk_treatments

Junction: risks to treatments. Supports primary treatment designation.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| risk_id | uuid | NO | | FK to risks |
| treatment_id | uuid | NO | | FK to treatments |
| is_primary | boolean | NO | false | |
| linked_at | timestamptz | NO | now() | |
| linked_by | uuid | YES | | |

**Constraints:** UNIQUE on (risk_id, treatment_id).

### risk_policy_links

Junction: risks to policies.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| policy_id | uuid | NO | | FK to policies |
| risk_id | uuid | NO | | FK to risks |
| linked_at | timestamptz | NO | now() | |
| linked_by | uuid | YES | | |

**Constraints:** UNIQUE on (policy_id, risk_id).

---

## 4. Domain 3: Control Management

Controls are modelled at three levels, per [codified-rules §8.1](../specification/codified-rules.md).
A single flat `controls` table cannot express the distinction that matters most in
scoring: a control is only as effective as the place it actually runs.

| Level | Table | Answers | Lifecycle |
|---|---|---|---|
| 1 | `control_objectives` | *What* must be achieved | Design → Implementation → Operating → Failure → Redesign → Deprecated |
| 2 | `control_activities` | *How* it is implemented | Draft → Active → Suspended → Retired |
| 3 | `control_deployments` | *Where* it runs | Planned → Active → Degraded → Failed → Decommissioned |

**Control effectiveness lives on the deployment, never on the objective.** A control
deployed on twelve assets has twelve CE ratings, and the objective's effective CE is
the *worst* of them (CINV-6). Averaging would let strong deployments mask the weak
one, which is precisely the asset an attacker reaches first.

### control_objectives

Level 1. What the control must achieve. Owned by a Control Owner.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| reference | text | NO | | Human-readable ID (e.g. CTL-001). UNIQUE. |
| title | text | NO | | |
| description | text | YES | | |
| family | text | NO | 'Governance' | Control family. Configuration-driven taxonomy, validated at the service layer so a change needs no migration. |
| control_type | text | NO | 'Preventive' | Preventive/Detective/Corrective. Configuration-driven. |
| lifecycle_state | text | NO | 'Design' | CHECK: Design/Implementation/Operating/Failure/Redesign/Deprecated |
| control_owner_id | uuid | YES | | RINV-3 and CINV-3 check this against linked risk owners |
| objective_statement | text | YES | | What "working" means, in terms a test can be written against. `description` says what the control is; this says how you would know it works |
| automation_level | text | NO | 'Manual' | Manual/Semi_Automated/Automated. **CINV-11** caps CE by this |
| implementation_type | text | NO | 'Technical' | Technical/Administrative/Physical. Orthogonal to preventive/detective/corrective |
| operating_frequency | text | NO | 'Continuous' | How often the control **runs**, as distinct from `test_frequency` on the deployment, which is how often somebody checks it ran |
| assurance_method | text | NO | 'Inquiry' | Inquiry/Observation/Inspection/Re_Performance, weakest first. **CINV-12** sets a floor for key controls |
| is_key_control | boolean | NO | false | Key controls carry the assurance floor |
| failure_declared_at | timestamptz | YES | | Set by the OL-5 cascade |
| remediation_plan | text | YES | | Required to leave Failure |
| deprecation_rationale | text | YES | | Required to reach Deprecated |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:** `ck_control_objectives_lifecycle_state`, UNIQUE on `reference`.

### control_activities

Level 2. How the objective is implemented. Owned by a Control Operator.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| reference | text | NO | | UNIQUE |
| objective_id | uuid | NO | | FK to control_objectives. ON DELETE CASCADE. |
| title | text | NO | | |
| description | text | YES | | |
| lifecycle_state | text | NO | 'Draft' | CHECK: Draft/Active/Suspended/Retired |
| control_operator_id | uuid | YES | | |
| suspension_rationale | text | YES | | Required to reach Suspended |
| automation_level | text | YES | | May differ from the objective's headline figure: an objective met by a nightly job on one estate and a spreadsheet on another is the normal case |
| operating_frequency | text | YES | | |
| procedure_ref | text | YES | | Where the runbook lives. An activity whose procedure nobody can produce is a description of an intention |
| tooling | text | YES | | Which system performs or records it |
| evidence_type | text | YES | | What this activity produces when it runs. Declaring it up front is what makes a missing artefact detectable rather than arguable |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:** `ck_control_activities_lifecycle_state`, UNIQUE on `reference`.

### control_deployments

Level 3. Where the control runs, on which asset. **CE lives here.**

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| reference | text | NO | | UNIQUE |
| activity_id | uuid | NO | | FK to control_activities. ON DELETE CASCADE. |
| attack_surface_id | uuid | NO | | FK to attack_surfaces. ON DELETE RESTRICT: an asset with live deployments cannot be deleted out from under them (CINV-9). |
| deployment_status | text | NO | 'Planned' | CHECK: Planned/Active/Degraded/Failed/Decommissioned |
| ce_rating | text | NO | 'CE-Unvalidated' | CHECK: CE-High/CE-Medium/CE-Low/CE-Unvalidated |
| ce_evidence_ref | text | YES | | CINV-1 at the schema layer: see constraint below |
| ce_assessed_by | uuid | YES | | |
| ce_assessed_at | date | YES | | Drives CE expiry (CINV-10) |
| ce_notes | text | YES | | |
| test_frequency | text | NO | 'Quarterly' | Configuration-driven cadence |
| last_test_result | text | NO | 'Not_Tested' | CHECK: Not_Tested/Pass/Partial/Fail |
| last_tested_date | date | YES | | |
| next_test_due | date | YES | | |
| decommission_rationale | text | YES | | Required to reach Decommissioned |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:**

| Constraint | Purpose | Invariant |
|---|---|---|
| `uq_deployment_activity_asset` | UNIQUE (activity_id, attack_surface_id): one deployment of an activity per asset | |
| `ck_control_deployments_status` | Valid deployment states | |
| `ck_control_deployments_ce_rating` | Valid CE vocabulary | |
| `ck_control_deployments_test_result` | Valid test results | |
| `ck_control_deployments_ce_evidence_required` | `ce_rating = 'CE-Unvalidated' OR ce_evidence_ref IS NOT NULL` | **CINV-1** |

> **On the CE vocabulary.** `CE-High`, `CE-Medium`, `CE-Low`, `CE-Unvalidated`. The
> names are fixed, because invariants and `CHECK` constraints reference them by
> name. What each one *buys*, the maximum likelihood reduction it permits, is
> configuration. See [scoring-model.md](../specification/scoring-model.md) §4.

### control_tests

Immutable test history. **Append-only, enforced by database trigger (CINV-7).**

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| deployment_id | uuid | NO | | FK to control_deployments. Tests attach to the deployment, not the objective. |
| result | text | NO | | CHECK: Not_Tested/Pass/Partial/Fail |
| evidence_ref | text | YES | | |
| notes | text | YES | | |
| tested_by | uuid | YES | | |
| tested_at | timestamptz | NO | now() | |
| supersedes_id | uuid | YES | | A correction references the record it replaces rather than editing it |
| sequence | integer | NO | 1 | Ordering within a deployment's history |

**Immutability:** `trg_control_tests_append_only` is a `BEFORE UPDATE OR DELETE`
trigger that raises `restrict_violation`. A service-layer rule cannot deliver this,
because anyone holding a database connection bypasses the service layer.

### attack_surfaces

Asset register. Named "attack surfaces" in the implementation; maps to the "Asset" terminology in the specification.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO | | UNIQUE |
| tier | text | NO | | Criticality tier. CHECK constraint. |
| description | text | YES | | |
| system_owner_id | uuid | YES | | |
| compliance_scopes | jsonb | NO | '[]' | Framework ids this asset sits inside. **AINV-2** reads it to decide where a control must run for a requirement to count; **AINV-9** refuses to report coverage for a framework no asset has claimed |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

---

## 5. Domain 4: Treatment Management

### treatments

Treatment plans linked to risks. Tracks lifecycle, cost, effort, and effectiveness.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| treatment_id | text | NO | | Human-readable ID. UNIQUE. |
| title | text | NO | | |
| description | text | YES | | |
| treatment_type | text | NO | 'Mitigate' | Mitigate/Transfer/Avoid/Accept |
| lifecycle_state | text | NO | 'Proposed' | |
| loe | text | YES | | Level of effort category |
| estimated_cost | numeric | YES | | |
| treatment_owner_id | uuid | YES | | |
| treatment_owner_name | text | YES | | Denormalised for display |
| treatment_owner_email | text | YES | | Denormalised for display |
| target_date | date | YES | | |
| check_in_frequency | text | YES | | |
| last_checkin_at | timestamptz | YES | | |
| next_checkin_due | date | YES | | |
| secarch_validated | boolean | NO | false | RINV-12: GRC Engineer validation |
| expected_impact_delta | integer | NO | 0 | |
| expected_likelihood_delta | integer | NO | 0 | |
| effectiveness_level | text | YES | | |
| implementation_type | text | YES | | |
| loe_implementation_hours | integer | YES | | |
| loe_operational_hours_pa | integer | YES | | |
| cost_implementation_usd | numeric | YES | | |
| cost_operational_usd_pa | numeric | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### treatment_approvals

Approval workflow for treatment plans and date extensions.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| treatment_id | uuid | NO | | FK to treatments |
| approval_type | text | NO | 'treatment_approval' | |
| requested_by | uuid | YES | | |
| assigned_to | uuid | YES | | |
| proposed_new_date | date | YES | | For date extension requests |
| decision | text | NO | 'Pending' | Pending/Approved/Rejected |
| decision_by | uuid | YES | | |
| decision_at | timestamptz | YES | | |
| decision_notes | text | YES | | |
| created_at | timestamptz | NO | now() | |

### treatment_checkins

Progress check-in records for active treatments.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| treatment_id | uuid | NO | | FK to treatments |
| status | text | NO | | |
| notes | text | NO | | |
| submitted_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |

---

## 6. Domain 5: Policy and Standards

### policies

Policy register with versioned content and compliance mapping.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| policy_id | text | NO | | Human-readable ID. UNIQUE. |
| title | text | NO | | |
| policy_type | text | NO | 'Information_Security' | |
| version | text | NO | '1.0' | |
| lifecycle_state | text | NO | 'Draft' | Draft/Under_Review/Active/Under_Revision/Deprecated |
| review_cycle | text | YES | 'Annual' | |
| effective_date | date | YES | | |
| next_review_date | date | YES | | |
| scope | text | YES | | |
| purpose | text | YES | | |
| body | text | YES | | Plain text content |
| content_rich_text | text | YES | | Rich text / HTML content |
| compliance_mappings | jsonb | NO | '[]' | Linked compliance frameworks |
| exception_count | integer | NO | 0 | |
| policy_owner_id | uuid | YES | | |
| approved_by | uuid | YES | | PINV-5: must be CISO or above |
| approved_at | timestamptz | YES | | |
| edited_by | uuid | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### standards

Technical standards linked to parent policies.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| standard_id | text | NO | | Human-readable ID. UNIQUE. |
| title | text | NO | | |
| parent_policy_id | uuid | YES | | FK to policies |
| version | text | NO | '1.0' | |
| lifecycle_state | text | NO | 'Draft' | |
| review_cycle | text | YES | 'Annual' | |
| scope | text | YES | | |
| body | text | YES | | |
| compliance_mappings | jsonb | NO | '[]' | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### policy_versions

Immutable version history. PINV-9: no UPDATE or DELETE.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| policy_id | uuid | NO | | FK to policies |
| version | text | NO | | |
| body | text | YES | | |
| content_rich_text | text | YES | | |
| change_summary | text | YES | | |
| edited_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |

### policy_exceptions

Time-bound exceptions to policy requirements. PINV-2: expiry_date NOT NULL.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| exception_id | text | NO | | Human-readable ID. UNIQUE. |
| parent_policy_id | uuid | NO | | FK to policies |
| title | text | NO | | |
| business_justification | text | NO | | |
| risk_statement | text | YES | | |
| compensating_controls | text | YES | | |
| requested_by | uuid | YES | | |
| approved_by | uuid | YES | | |
| lifecycle_state | text | NO | 'Requested' | Requested/Approved/Rejected/Expired |
| expiry_date | date | NO | | PINV-2: always time-bound |
| rmf_promotion_link | uuid | YES | | FK to risks if promoted |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### policy_controls

Junction: policies to controls.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| policy_id | uuid | NO | | FK to policies |
| control_id | uuid | NO | | FK to controls |
| linked_at | timestamptz | NO | now() | |
| linked_by | uuid | YES | | |

**Constraints:** UNIQUE on (policy_id, control_id).

### policy_ai_assessments

AI-generated policy analysis records.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| policy_id | uuid | NO | | FK to policies |
| assessment_type | text | NO | 'content_review' | |
| policy_version | text | NO | | |
| policy_content_snapshot | text | YES | | Frozen content at assessment time |
| linked_controls_snapshot | jsonb | YES | '[]' | |
| linked_risks_snapshot | jsonb | YES | '[]' | |
| assessment_summary | text | YES | | |
| total_recommendations | integer | YES | 0 | |
| high_priority_count | integer | YES | 0 | |
| medium_priority_count | integer | YES | 0 | |
| low_priority_count | integer | YES | 0 | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### policy_ai_recommendations

Individual recommendations from AI assessments.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| assessment_id | uuid | NO | | FK to policy_ai_assessments |
| recommendation_type | text | NO | | CHECK constraint |
| title | text | NO | | |
| description | text | NO | | |
| suggested_content | text | YES | | |
| priority | text | NO | | CHECK constraint: high/medium/low |
| is_applied | boolean | YES | false | |
| applied_at | timestamptz | YES | | |
| applied_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |

---

## 7. Domain 6: Vendor and Third-Party Risk

### vendors

Vendor register. Central record for all third-party providers.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| vendor_id | text | NO | | Human-readable ID |
| name | text | NO | | |
| description | text | YES | | |
| website | text | YES | | |
| hq_country | text | YES | | |
| tier | text | YES | 'Unrated' | Criticality tier |
| lifecycle_state | text | YES | 'Active' | |
| primary_contact_name | text | YES | | |
| primary_contact_email | text | YES | | |
| business_owner_id | uuid | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### engagements

Vendor assessment lifecycle. The core state machine for TPRM. Supports lifecycle from Intake through Offboarding.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | text | NO | | Human-readable ID |
| vendor_id | uuid | NO | | FK to vendors |
| service_name | text | NO | | |
| service_description | text | YES | | |
| lifecycle_state | engagement_lifecycle (enum) | YES | 'Intake' | |
| risk_tier | text | YES | | Determined by IRA |
| business_owner_id | uuid | YES | | |
| tprm_analyst_id | uuid | YES | | |
| security_reviewer_id | uuid | YES | | |
| exec_approval_status | text | YES | 'Not_Required' | |
| exec_approval_required | boolean | YES | false | |
| exec_decision_at | timestamptz | YES | | |
| exec_decision_by | uuid | YES | | |
| exec_decision_notes | text | YES | | |
| contract_start_date | date | YES | | |
| contract_end_date | date | YES | | |
| next_review_date | date | YES | | |
| data_classification | text | YES | | |
| hosting_model | text | YES | | |
| integration_type | text | YES | | |
| escalation_flag | boolean | YES | false | |
| offboarding_initiated_at | timestamptz | YES | | |
| promoted_risk_id | uuid | YES | | FK to risks (promoted findings) |
| risk_promoted_at | timestamptz | YES | | |
| risk_promoted_by | uuid | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### ira_assessments

Inherent Risk Assessment. Scored questionnaire determining vendor risk tier.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | uuid | NO | | FK to engagements |
| status | text | YES | 'draft' | |
| answers | jsonb | YES | '{}' | Questionnaire responses |
| section_scores | jsonb | YES | '{}' | Per-section scoring |
| overall_score | numeric | YES | | |
| final_tier | text | YES | | Determined tier |
| elevator_log | jsonb | YES | '[]' | Manual tier adjustments with rationale |
| assessed_by | uuid | YES | | |
| completed_at | timestamptz | YES | | |
| confirmed_at | timestamptz | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### dd_artefacts

Due diligence documents collected from vendors.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | uuid | NO | | FK to engagements |
| name | text | NO | | |
| category | text | YES | | |
| artefact_type | text | YES | | |
| tier_required | text | YES | | Which tier requires this artefact |
| artefact_class | text | YES | | |
| status | text | YES | 'Requested' | Requested/Received/Reviewed/Accepted/Rejected |
| file_path | text | YES | | |
| uploaded_by | uuid | YES | | |
| reviewed_by | uuid | YES | | |
| review_notes | text | YES | | |
| date_requested | date | YES | | |
| date_received | date | YES | | |
| review_date | date | YES | | |
| expiry_date | date | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### dd_findings

Findings from due diligence review. Can be promoted to risk register.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | uuid | NO | | FK to engagements |
| finding_id | text | YES | | Human-readable ID |
| title | text | NO | | |
| description | text | YES | | |
| severity | text | YES | 'Low' | |
| status | text | YES | 'open' | |
| remediation_plan | text | YES | | |
| remediation_due_date | date | YES | | |
| ciso_exception_required | boolean | YES | false | |
| found_by | uuid | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### approval_decisions

Approval workflow for vendor engagements (executive approval, risk acceptance).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | uuid | NO | | FK to engagements |
| decision_type | text | NO | | |
| decision | text | YES | 'Pending' | |
| decided_by | uuid | YES | | |
| decided_at | timestamptz | YES | | |
| notes | text | YES | | |
| conditions | text | YES | | |
| created_at | timestamptz | YES | now() | |

### offboarding_checklist

Structured checklist for vendor offboarding.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| engagement_id | uuid | NO | | FK to engagements |
| item_number | integer | NO | | UNIQUE with engagement_id |
| item_description | text | NO | | |
| confirmed | boolean | YES | false | |
| confirmed_at | timestamptz | YES | | |
| confirmed_by | uuid | YES | | |
| notes | text | YES | | |
| created_at | timestamptz | YES | now() | |
| updated_at | timestamptz | YES | now() | |

### analyst_tasks

Task management for TPRM analysts. Links to engagements, vendors, findings, and assessments.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| title | text | NO | | |
| description | text | YES | | |
| task_type | text | NO | | CHECK constraint |
| status | text | NO | 'todo' | CHECK constraint |
| assigned_to | uuid | YES | | |
| created_by | uuid | YES | | |
| engagement_id | uuid | YES | | FK to engagements |
| vendor_id | uuid | YES | | FK to vendors |
| finding_id | uuid | YES | | FK to dd_findings |
| ira_id | uuid | YES | | FK to ira_assessments |
| due_date | date | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

---

## 8. Domain 7: Threat Management

Threat modelling is bound bidirectionally to GRC state. A scenario is Mitigated only
while the control that mitigates it is genuinely operating; when that control fails,
the scenario re-opens and the model loses its sign-off ([codified-rules §20.2](../specification/codified-rules.md)).
A mitigation makes the linked risk record eligible for re-evaluation (§20.3).

The environment a model sits in, meaning the controls already deployed on the
asset and the risks already recorded against it, is surfaced to the modeller as
**read-only context**. No table below carries a column written by that context
engine, and that absence is deliberate: see §19.4 and TINV-7.

### threat_models

Primary container for a system or feature threat model.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| reference | text | NO | | Human-readable ID (e.g. TM-001). UNIQUE. |
| title | text | NO | | |
| attack_surface_id | uuid | NO | | FK to attack_surfaces. ON DELETE RESTRICT. |
| lifecycle_state | text | NO | 'Scope' | CHECK: Scope/Decomposition/Threat_Analysis/Mitigation_Design/Review/Active/Deprecated/Abandoned |
| methodology | text | NO | 'STRIDE' | Default categorisation method |
| description | text | YES | | |
| system_owner_id | uuid | NO | | Accountable for the system |
| appsec_partner_id | uuid | YES | | Advisory; distinct from the signer |
| appsec_signoff_by | uuid | YES | | TINV-2. Team membership, not a named individual. |
| appsec_signoff_at | timestamptz | YES | | |
| owner_signoff_by | uuid | YES | | TINV-2 |
| owner_signoff_at | timestamptz | YES | | |
| signoff_stripped_reason | text | YES | | Set when the §20.2 cascade revokes sign-off |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:**

| Constraint | Purpose | Invariant |
|---|---|---|
| `ck_threat_models_lifecycle_state` | Valid lifecycle states | |
| `ck_threat_models_appsec_independent` | `appsec_signoff_by IS NULL OR appsec_signoff_by <> system_owner_id` | **TINV-2** |

> **Two signature pairs, not one.** The original single `signoff_by` column could not
> express independent sign-off, which is the entire point of TINV-2. The system owner
> attests that the model describes their system; AppSec attests that the analysis is
> sound. One person doing both is a review with one participant.

### threat_components

Data Flow Diagram elements. A component is not a box on a diagram: what it handles
and where it sits determine what a compromise costs and which boundary it crosses.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| threat_model_id | uuid | NO | | FK to threat_models. ON DELETE CASCADE. |
| name | text | NO | | |
| component_type | text | NO | | CHECK: Process/Datastore/External_Entity/Data_Flow/Trust_Boundary |
| description | text | YES | | |
| data_classification | text | YES | | Configuration-driven, ordered least to most sensitive. The *order* is what TINV-9 and TINV-11 read. |
| data_types | jsonb | NO | '[]' | Data categories handled. Drives the regulatory view of a compromise. |
| trust_zone | text | YES | | Where it sits. Each zone carries a trust level. **TINV-9**: required at or above the sensitive threshold. |
| exposure | text | YES | | How reachable it is. Informs, never sets, severity. |
| attack_surface_id | uuid | YES | | FK to attack_surfaces, ON DELETE SET NULL. May differ from the model's primary asset, which is exactly where cross-boundary flows get interesting. |
| source_component_id | uuid | YES | | For Data_Flow components: origin |
| target_component_id | uuid | YES | | For Data_Flow components: destination |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:** `ck_threat_components_type`. Classification, zone and exposure are
validated at the **service** layer against the configured taxonomy, deliberately not
by `CHECK` constraints, so an organisation can use its own data model without a
schema migration.

### threat_scenarios

Identified threats mapped to components.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| reference | text | NO | | UNIQUE |
| threat_model_id | uuid | NO | | FK to threat_models. ON DELETE CASCADE. |
| component_id | uuid | NO | | FK to threat_components. ON DELETE CASCADE. |
| category | text | NO | | CHECK: STRIDE category |
| description | text | NO | | |
| inherent_severity | text | NO | | CHECK: Critical/High/Medium/Low |
| status | text | NO | 'Identified' | CHECK: Identified/Mitigated/Accepted/Promoted_To_Risk |
| remediation_target_date | date | YES | | Drives §20.2 auto-promotion |
| acceptance_expiry | date | YES | | **TINV-5** |
| acceptance_rationale | text | YES | | **TINV-10** |
| promoted_risk_id | uuid | YES | | FK to risks, ON DELETE SET NULL. **TINV-6** |
| status_rationale | text | YES | | Reason for the most recent status change. A decision without a reason is not auditable (**TINV-10**). |
| reopened_reason | text | YES | | Set by the control-failure cascade, or by a person re-opening deliberately |
| reopened_at | timestamptz | YES | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

**Constraints:**

| Constraint | Purpose | Invariant |
|---|---|---|
| `ck_threat_scenarios_status` | Valid status values | |
| `ck_threat_scenarios_severity` | Valid severity values | |
| `ck_threat_scenarios_category` | Valid STRIDE categories | |
| `ck_threat_scenarios_no_local_acceptance_above_low` | `status <> 'Accepted' OR inherent_severity = 'Low'` | **TINV-3** |
| `ck_threat_scenarios_acceptance_time_bound` | `status <> 'Accepted' OR acceptance_expiry IS NOT NULL` | **TINV-5** |
| `ck_threat_scenarios_promotion_linked` | `status <> 'Promoted_To_Risk' OR promoted_risk_id IS NOT NULL` | **TINV-6** |

> **There is no `Partially_Mitigated` status.** Partial coverage is derived from the
> link table and displayed as a UI state, never stored as a status (TM-PARTIAL). A
> partially mitigated threat is an open threat with work in progress, and giving it a
> status of its own would let it satisfy TINV-1.

### threat_mitigation_links

Junction mapping a scenario to the **deployed** control that mitigates it.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| scenario_id | uuid | NO | | FK to threat_scenarios. ON DELETE CASCADE. |
| deployment_id | uuid | NO | | FK to **control_deployments**. ON DELETE CASCADE. |
| effectiveness_assurance | text | NO | 'Fully_Mitigated' | CHECK: Fully_Mitigated/Partially_Mitigated |
| linked_by | uuid | YES | | |
| linked_at | timestamptz | NO | now() | |

**Constraints:** `uq_threat_mitigation` UNIQUE (scenario_id, deployment_id),
`ck_threat_mitigation_assurance`.

> **The FK targets `control_deployments`, not a control objective.** This is the single
> most consequential modelling decision in the threat domain. An objective is an
> intention; a deployment is the instance running on the asset the component sits on.
> Linking to an objective would let a scenario be "mitigated" by a control that exists
> everywhere except where the threat is. It also gives §20.2 something to fire on: the
> deployment that fails re-opens exactly the scenarios that depended on it.

### threat_scenario_comments

Threaded discussion on a scenario. Threat modelling is a conversation between AppSec,
engineering and risk, and the conversation is part of the record, not a side channel
in a chat tool that nobody can produce at audit.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| scenario_id | uuid | NO | | FK to threat_scenarios. ON DELETE CASCADE. |
| parent_comment_id | uuid | YES | | FK to threat_scenario_comments, self-referential threading |
| body | text | NO | | |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### threat_scenario_evidence

Evidence attached to a scenario. **Append-only, enforced by database trigger.**

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| scenario_id | uuid | NO | | FK to threat_scenarios. ON DELETE CASCADE. |
| title | text | NO | | |
| evidence_ref | text | NO | | A reference: scan result, design document, test report, ticket. Artefact storage is the organisation's concern. |
| evidence_type | text | YES | | |
| supports | text | YES | | What the evidence was offered for, so an assessor can see whether the claim and the proof match |
| notes | text | YES | | |
| supersedes_id | uuid | YES | | Superseding creates a new record referencing the original |
| created_by | uuid | YES | | |
| created_at | timestamptz | NO | now() | |

**Immutability:** `trg_threat_scenario_evidence_append_only`. Evidence that can be
edited after the fact is not evidence: the same argument as CINV-7 and PINV-9.

### threat_scenario_risk_links

Scenario to **existing** risk record. Distinct from promotion.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| scenario_id | uuid | NO | | FK to threat_scenarios. ON DELETE CASCADE. |
| risk_id | uuid | NO | | FK to risks. ON DELETE CASCADE: the link goes, never the register entry. |
| link_type | text | NO | 'Represents' | Configuration-driven. Exactly one configured type may carry `creates_risk: true`. |
| rationale | text | YES | | |
| linked_by | uuid | YES | | |
| linked_at | timestamptz | NO | now() | |

**Constraints:** `uq_threat_scenario_risk` UNIQUE (scenario_id, risk_id).

> **Why this table exists.** Most threats on a mature system map onto exposures the
> register already carries. Without a way to say "this risk already covers it", every
> threat model either duplicates the register or leaves scenarios unresolved. Linking
> and promoting are therefore distinct operations, and TINV-8 forbids doing both.

---

## 9. Domain 8: Compliance and Assurance

The register holds framework **requirements** as records rather than deriving
compliance from the policies that reference a control. See
[codified-rules Part 6](../specification/codified-rules.md).

### compliance_frameworks

One framework at one version. Version is part of the identity, not an attribute.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| framework_id | text | NO | | Natural key from the catalogue file, e.g. `NIST-CSF-2.0`. UNIQUE |
| name | text | NO | | |
| version | text | NO | | **AINV-7**: immutable once requirements are loaded |
| authority | text | YES | | |
| source_url | text | YES | | |
| redistributable | boolean | NO | false | **AINV-6**: false means this repository may not carry the requirement text, and the loader refuses a catalogue that does |
| licence_note | text | YES | | |
| adopted | boolean | NO | false | **AINV-8**: only an adopted framework carries assessed positions |
| adopted_at | timestamptz | YES | | |

### compliance_requirements

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| framework_id | uuid | NO | | FK to compliance_frameworks. ON DELETE CASCADE |
| ref | text | NO | | The identifier as the framework writes it: `GV.OC-01`, `A.5.15`, `8.3.1`. UNIQUE per framework |
| title | text | NO | | |
| requirement_text | text | YES | | Full prose. **NULL for a licensed framework**; populated by an operator importing from their own copy |
| category | text | YES | | Grouping, e.g. `Protect / Data Security` |
| sort_order | integer | NO | 0 | |

### requirement_assessments

The organisation's position on one requirement. A Statement of Applicability entry.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| requirement_id | uuid | NO | | FK to compliance_requirements. UNIQUE: exactly one position per requirement |
| lifecycle_state | text | NO | 'Not_Assessed' | CHECK: Not_Assessed/Not_Applicable/Applicable/Covered/Compensating/Gap |
| rationale | text | YES | | **AINV-1**: required for Not_Applicable |
| owner_id | uuid | YES | | |
| assessed_by | uuid | YES | | |
| assessed_at | timestamptz | YES | | |
| compensating_expiry | date | YES | | **AINV-4**: required for Compensating |
| gap_reason | text | YES | | Set by the §24.3 cascade, so the reason a requirement became a gap survives |

**Constraints:**

| Constraint | Purpose | Invariant |
|---|---|---|
| `ck_requirement_assessments_state` | Valid states | |
| `ck_requirement_assessments_exclusion_justified` | `lifecycle_state <> 'Not_Applicable' OR rationale IS NOT NULL` | **AINV-1** |
| `ck_requirement_assessments_compensating_time_bound` | `lifecycle_state <> 'Compensating' OR compensating_expiry IS NOT NULL` | **AINV-4** |

> **`Not_Assessed` is a real state, not a missing row.** "Nobody has looked at
> this" is itself a finding, and a finding that cannot be counted does not get
> fixed. Deriving the position from the absence of a record would make the most
> common state in any real register invisible.

### control_requirement_links

A person's assertion that a control objective addresses a requirement.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| objective_id | uuid | NO | | FK to control_objectives. ON DELETE CASCADE |
| requirement_id | uuid | NO | | FK to compliance_requirements. ON DELETE CASCADE |
| coverage_level | text | NO | 'Full' | Configuration-driven. Full/Partial/Compensating by default; **AINV-3** reads `satisfies` from configuration rather than from the name |
| rationale | text | YES | | |
| asserted_by | uuid | YES | | |
| asserted_at | timestamptz | NO | now() | |

**Constraints:** `uq_control_requirement` UNIQUE (objective_id, requirement_id).

> **Nothing infers a link.** Not a shared policy, not a matching control family,
> not a keyword. Somebody asserts it and the record says who: the same argument
> TINV-7 makes about threat mitigation, for the same reason: an inferred control
> is one nobody has checked.

> **The dependency points one way.** `control_requirement_links` references
> `control_objectives`, and the control module carries no relationship back.
> A back-reference would make importing `control.models` fail unless
> `compliance.models` had already been imported, which is a coupling the module
> boundary exists to prevent.

---

## 10. Foreign Key Relationship Map

55 foreign key relationships across the schema.

| Source Table | Source Column | Target Table | Target Column |
|---|---|---|---|
| risk_comments | risk_id | risks | id |
| risk_comments | parent_comment_id | risk_comments | id |
| risk_attachments | risk_id | risks | id |
| risk_phase_history | risk_id | risks | id |
| risk_reviews | risk_id | risks | id |
| risk_assets | risk_id | risks | id |
| risk_assets | attack_surface_id | attack_surfaces | id |
| risk_controls | risk_id | risks | id |
| risk_controls | control_id | control_objectives | id |
| risk_treatments | risk_id | risks | id |
| risk_treatments | treatment_id | treatments | id |
| risk_policy_links | policy_id | policies | id |
| risk_policy_links | risk_id | risks | id |
| treatment_approvals | treatment_id | treatments | id |
| treatment_checkins | treatment_id | treatments | id |
| standards | parent_policy_id | policies | id |
| policy_exceptions | parent_policy_id | policies | id |
| policy_controls | policy_id | policies | id |
| policy_controls | control_id | control_objectives | id |
| policy_versions | policy_id | policies | id |
| policy_ai_assessments | policy_id | policies | id |
| policy_ai_recommendations | assessment_id | policy_ai_assessments | id |
| engagements | vendor_id | vendors | id |
| engagements | promoted_risk_id | risks | id |
| ira_assessments | engagement_id | engagements | id |
| dd_artefacts | engagement_id | engagements | id |
| dd_findings | engagement_id | engagements | id |
| approval_decisions | engagement_id | engagements | id |
| offboarding_checklist | engagement_id | engagements | id |
| analyst_tasks | engagement_id | engagements | id |
| analyst_tasks | vendor_id | vendors | id |
| analyst_tasks | finding_id | dd_findings | id |
| analyst_tasks | ira_id | ira_assessments | id |
| user_group_members | group_id | user_groups | id |
| threat_models | attack_surface_id | attack_surfaces | id |
| threat_components | threat_model_id | threat_models | id |
| threat_scenarios | threat_model_id | threat_models | id |
| threat_scenarios | component_id | threat_components | id |
| threat_scenarios | promoted_risk_id | risks | id |
| threat_mitigation_links | scenario_id | threat_scenarios | id |
| threat_mitigation_links | deployment_id | control_deployments | id |
| threat_components | attack_surface_id | attack_surfaces | id |
| threat_scenario_comments | scenario_id | threat_scenarios | id |
| threat_scenario_comments | parent_comment_id | threat_scenario_comments | id |
| threat_scenario_evidence | scenario_id | threat_scenarios | id |
| threat_scenario_risk_links | scenario_id | threat_scenarios | id |
| threat_scenario_risk_links | risk_id | risks | id |
| control_activities | objective_id | control_objectives | id |
| control_deployments | activity_id | control_activities | id |
| control_deployments | attack_surface_id | attack_surfaces | id |
| control_tests | deployment_id | control_deployments | id |
| compliance_requirements | framework_id | compliance_frameworks | id |
| requirement_assessments | requirement_id | compliance_requirements | id |
| control_requirement_links | requirement_id | compliance_requirements | id |
| control_requirement_links | objective_id | control_objectives | id |

---

## 11. Schema-Level Constraint Summary

| Constraint Type | Count | Purpose |
|---|---|---|
| PRIMARY KEY | 49 | One per table |
| UNIQUE | 23 | Human-readable IDs, junction table deduplication, role assignment uniqueness |
| CHECK (named, non-NOT-NULL) | 37 | Enum validation on lifecycle states, ratings, scores, tiers, strategies; plus the conditional CHECKs carrying an invariant |
| FOREIGN KEY | 55 | Cross-entity integrity |
| NOT NULL | ~210 | Field-level data integrity |
| APPEND-ONLY TRIGGER | 6 | Immutability on audit_log, risk_phase_history, policy_versions, control_tests, treatment_checkins, threat_scenario_evidence |

### Named CHECK Constraints on risks table

| Constraint | Purpose | Invariant |
|---|---|---|
| risks_phase_check | Valid phase values (1-7) | RINV-8 |
| risks_lifecycle_state_check | Valid lifecycle states | |
| risks_intake_source_check | Valid intake sources | |
| risks_risk_level_check | Valid risk levels | |
| risks_tier_check | Valid NIST RMF tiers | |
| risks_impact_check | Impact range 1-5 | |
| risks_likelihood_check | Likelihood range 1-5 | |
| risks_inherent_rating_check | Valid rating bands | |
| risks_ce_rating_check | Valid CE values | |
| risks_residual_impact_check | Residual impact range 1-5 | |
| risks_residual_likelihood_check | Residual likelihood range 1-5 | |
| risks_residual_rating_check | Valid residual rating bands | |
| risks_treatment_strategy_check | Accept/Mitigate/Transfer/Avoid | RINV-5 (service backup) |
| risks_sla_status_check | Valid SLA status values | |
| risks_expected_residual_impact_check | Expected residual range 1-5 | |
| risks_expected_residual_likelihood_check | Expected residual range 1-5 | |

---

## 12. Invariant Enforcement at Schema Layer

Cross-reference to [Invariants Catalogue](../specification/invariants-catalogue.md). Only schema-enforced invariants listed here. Service-layer invariants are enforced in the API and are not visible in the DDL.

| Invariant | Schema Enforcement | Mechanism |
|---|---|---|
| RINV-1 | `residual_score_locked` defaults true; while locked, residual may not diverge from inherent | CHECK + service |
| RINV-4 | Acceptance requires an expiry date; the service caps the window per rating | CHECK + service |
| RINV-5 | `risks_treatment_strategy_check` limits valid values; Accept is rejected on a Critical rating | CHECK + service |
| RINV-10 | `risk_owner_id` and `risk_stakeholder_id`; service enforces presence from Phase 3 | CHECK + service |
| **SEP-1** | `risk_owner_id <> risk_stakeholder_id` on the risks table | CHECK |
| CINV-1 | `ce_rating = 'CE-Unvalidated' OR ce_evidence_ref IS NOT NULL` on control_deployments | CHECK |
| **CINV-7** | `control_tests`: append-only. `trg_control_tests_append_only` rejects UPDATE and DELETE | Trigger |
| PINV-2 | `policy_exceptions.expiry_date`: NOT NULL | NOT NULL |
| PINV-5 | Policy owner cannot be the approver | CHECK + service |
| PINV-9 | `policy_versions`: append-only. `trg_policy_versions_append_only` | Trigger |
| TINV-2 | `appsec_signoff_by IS NULL OR appsec_signoff_by <> system_owner_id` | CHECK |
| TINV-3 | `status <> 'Accepted' OR inherent_severity = 'Low'` | CHECK |
| TINV-5 | `status <> 'Accepted' OR acceptance_expiry IS NOT NULL` | CHECK |
| TINV-6 | `status <> 'Promoted_To_Risk' OR promoted_risk_id IS NOT NULL` | CHECK |
| TSE-1 | `threat_scenario_evidence`: append-only | Trigger |
| **AINV-1** | `lifecycle_state <> 'Not_Applicable' OR rationale IS NOT NULL` | CHECK |
| **AINV-4** | `lifecycle_state <> 'Compensating' OR compensating_expiry IS NOT NULL` | CHECK |

> **CINV-7 attaches to `control_tests`, not `risk_phase_history`.** CINV-7 is the
> control-testing immutability rule (§10.1, TST-1). `risk_phase_history` is also
> append-only, and for the same reason, but it is not what CINV-7 says. Both tables
> carry the trigger; only one of them is what the invariant is about.

**Append-only tables.** Six tables reject `UPDATE` and `DELETE` at the database layer
via `grc_reject_mutation()`: `audit_log`, `risk_phase_history`, `policy_versions`,
`control_tests`, `treatment_checkins`, `threat_scenario_evidence`. A service-layer
rule cannot deliver immutability, because anyone holding a database connection
bypasses the service layer. A trigger cannot be bypassed.

---

*This data model is released under CC BY 4.0. Adapt freely with attribution.*
