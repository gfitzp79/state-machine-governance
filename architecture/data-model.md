# Data Model

**Version:** 1.0 | **License:** CC BY 4.0
**Source:** Derived from [Codified Rules Specification](../specification/codified-rules.md) and validated against a working Supabase implementation.
**Purpose:** Complete relational schema for the governance platform. 35 tables across 6 domains. All FK relationships, named constraints, and schema-level invariant enforcement documented. Designed for implementation teams to reproduce the data layer with full traceability to the specification.

> **Design principle:** The schema is the first line of enforcement. Every NOT NULL, CHECK, UNIQUE, and FK constraint exists because a codified rule requires it. If a constraint is absent, the rule is not enforced at the data layer and must be enforced at the service layer. See [Invariants Catalogue](../specification/invariants-catalogue.md) for the complete enforcement mapping.

> **Implementation note:** This schema was built on PostgreSQL (Supabase). All tables use `uuid` primary keys with `gen_random_uuid()` defaults. Timestamps are `timestamptz` with `now()` defaults. Row Level Security (RLS) is enforced on all tables. The schema is portable to any PostgreSQL-compatible database. Adapt RLS and auth functions for non-Supabase environments.

---

## Table of Contents

1. [Schema Overview](#1-schema-overview)
2. [Domain 1: Platform and Identity](#2-domain-1-platform-and-identity)
3. [Domain 2: Risk Management](#3-domain-2-risk-management)
4. [Domain 3: Control Management](#4-domain-3-control-management)
5. [Domain 4: Treatment Management](#5-domain-4-treatment-management)
6. [Domain 5: Policy and Standards](#6-domain-5-policy-and-standards)
7. [Domain 6: Vendor and Third-Party Risk](#7-domain-6-vendor-and-third-party-risk)
8. [Foreign Key Relationship Map](#8-foreign-key-relationship-map)
9. [Schema-Level Constraint Summary](#9-schema-level-constraint-summary)
10. [Invariant Enforcement at Schema Layer](#10-invariant-enforcement-at-schema-layer)

---

## 1. Schema Overview

| Domain | Tables | Purpose |
|---|---|---|
| Platform and Identity | 7 | User profiles, roles, groups, audit logging, notifications, OIDC role mapping |
| Risk Management | 8 | Risk register, 7-phase lifecycle, phase history, comments, attachments, reviews, control links, treatment links, policy links |
| Control Management | 2 | Control library with CE lifecycle, asset register |
| Treatment Management | 3 | Treatment plans, approval workflows, progress check-ins |
| Policy and Standards | 7 | Policy register, standards, versions, exceptions, control links, AI assessments, AI recommendations |
| Vendor and Third-Party Risk | 8 | Vendor register, engagements (assessment lifecycle), inherent risk assessments, due diligence artefacts, findings, approval decisions, offboarding, analyst tasks |
| **Total** | **35** | |

### Entity Relationship Summary

```
profiles ←── user_roles
         ←── user_groups ←── user_group_members
         ←── role_mappings (OIDC)

risks ←── risk_phase_history
      ←── risk_comments (threaded)
      ←── risk_attachments
      ←── risk_reviews
      ←── risk_controls ──→ controls
      ←── risk_treatments ──→ treatments
      ←── risk_policy_links ──→ policies

controls ←── policy_controls ──→ policies
         ←── risk_controls ──→ risks

treatments ←── treatment_approvals
           ←── treatment_checkins
           ←── risk_treatments ──→ risks

policies ←── standards
         ←── policy_versions
         ←── policy_exceptions
         ←── policy_controls ──→ controls
         ←── policy_ai_assessments ←── policy_ai_recommendations
         ←── risk_policy_links ──→ risks

vendors ←── engagements ←── ira_assessments
                        ←── dd_artefacts
                        ←── dd_findings
                        ←── approval_decisions
                        ←── offboarding_checklist
                        ←── analyst_tasks
        ←── analyst_tasks (direct)

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
| pre_true_risk_confirmed | boolean | NO | false | Phase 2 gate |
| pre_materiality_classified | boolean | NO | false | Phase 2 gate |
| pre_risk_level_assigned | boolean | NO | false | Phase 2 gate |
| pre_stakeholders_identified | boolean | NO | false | Phase 2 gate |
| pre_ce_assessed | boolean | NO | false | Phase 2 gate |
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

### controls

Control library. Includes CE lifecycle, test history tracking, and asset linkage.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| cccf_id | text | NO | | Human-readable ID. UNIQUE. |
| title | text | NO | | |
| description | text | YES | | |
| family | text | NO | | Control family/category |
| control_type | text | NO | 'Preventive' | Preventive/Detective/Corrective |
| lifecycle_state | text | NO | 'Design' | Design/Implementation/Operating/Deprecated |
| ce_rating | text | NO | 'CE-Unvalidated' | CE-Effective/CE-Partially/CE-Ineffective/CE-Unvalidated |
| ce_assessed_by | uuid | YES | | |
| ce_assessed_at | timestamptz | YES | | |
| ce_evidence_ref | text | YES | | CINV-1: required when CE != Unvalidated |
| ce_notes | text | YES | | |
| test_result | text | YES | 'Not_Tested' | |
| last_tested_date | date | YES | | |
| next_test_due | date | YES | | |
| test_frequency | text | YES | | |
| control_owner_id | uuid | YES | | |
| attack_surface_ids | jsonb | NO | '[]' | Linked asset IDs |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

### attack_surfaces

Asset register. Named "attack surfaces" in the implementation; maps to the "Asset" terminology in the specification.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO | | UNIQUE |
| tier | text | NO | | Criticality tier. CHECK constraint. |
| description | text | YES | | |
| system_owner_id | uuid | YES | | |
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

## 8. Foreign Key Relationship Map

32 foreign key relationships across the schema.

| Source Table | Source Column | Target Table | Target Column |
|---|---|---|---|
| risk_comments | risk_id | risks | id |
| risk_comments | parent_comment_id | risk_comments | id |
| risk_attachments | risk_id | risks | id |
| risk_phase_history | risk_id | risks | id |
| risk_reviews | risk_id | risks | id |
| risk_controls | risk_id | risks | id |
| risk_controls | control_id | controls | id |
| risk_treatments | risk_id | risks | id |
| risk_treatments | treatment_id | treatments | id |
| risk_policy_links | policy_id | policies | id |
| risk_policy_links | risk_id | risks | id |
| treatment_approvals | treatment_id | treatments | id |
| treatment_checkins | treatment_id | treatments | id |
| standards | parent_policy_id | policies | id |
| policy_exceptions | parent_policy_id | policies | id |
| policy_controls | policy_id | policies | id |
| policy_controls | control_id | controls | id |
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

---

## 9. Schema-Level Constraint Summary

| Constraint Type | Count | Purpose |
|---|---|---|
| PRIMARY KEY | 35 | One per table |
| UNIQUE | 14 | Human-readable IDs, junction table deduplication, role assignment uniqueness |
| CHECK (named, non-NOT-NULL) | 22 | Enum validation on lifecycle states, ratings, scores, tiers, strategies |
| FOREIGN KEY | 32 | Cross-entity integrity |
| NOT NULL | ~180 | Field-level data integrity |

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

## 10. Invariant Enforcement at Schema Layer

Cross-reference to [Invariants Catalogue](../specification/invariants-catalogue.md). Only schema-enforced invariants listed here. Service-layer invariants are enforced in the API and are not visible in the DDL.

| Invariant | Schema Enforcement | Mechanism |
|---|---|---|
| RINV-4 | acceptance_expiry_date field exists. Service layer enforces NOT NULL when treatment_strategy = 'Accept'. | Conditional NOT NULL (service) |
| RINV-5 | risks_treatment_strategy_check limits valid values. Service layer rejects Accept when inherent_rating = Critical. | CHECK + service |
| RINV-10 | risk_owner_id and risk_stakeholder_id columns exist. Service enforces NOT NULL at phase transitions. | Service-enforced NOT NULL |
| CINV-7 | risk_phase_history: immutable by design (INSERT only, no UPDATE/DELETE in RLS). | RLS policy |
| PINV-2 | policy_exceptions.expiry_date: NOT NULL constraint. | Schema NOT NULL |
| PINV-9 | policy_versions: immutable by design (INSERT only, no UPDATE/DELETE in RLS). | RLS policy |

---

*This data model is released under CC BY 4.0. Adapt freely with attribution.*
