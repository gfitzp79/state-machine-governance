# GRC Platform Reference Architecture

**Version:** 1.0-template | **License:** CC BY 4.0
**Purpose:** Production-grade reference architecture for a state-machine governance platform. Covers the entity relationship model, risk lifecycle state machine, cascade propagation engine, RBAC model, deployment architecture, and integration roadmap. Designed for architecture teams to adapt to their own frameworks and infrastructure.

> **How to use this document:** This architecture implements the rules defined in the [Codified Rules Specification](../specification/codified-rules.md). All schema constraints, lifecycle gates, and invariants referenced here trace back to that specification. Replace `[CUSTOMISE]` blocks with your organisation's specifics.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Entity Relationship Model](#2-entity-relationship-model)
3. [Risk Lifecycle State Machine](#3-risk-lifecycle-state-machine)
4. [Cascade Propagation Engine](#4-cascade-propagation-engine)
5. [RBAC Model](#5-rbac-model)
6. [Deployment Architecture](#6-deployment-architecture)
7. [Agentic Engineering Method](#7-agentic-engineering-method)
8. [Integration Roadmap](#8-integration-roadmap)

---

## 1. Executive Summary

### The Problem

Legacy GRC tools treat governance as a document management problem, not a state management problem. When a control fails in production, nothing cascades. Risk scores stay stale. Analysts discover SLA breaches in quarterly reviews, not in real time. Compliance posture drifts silently between audit cycles.

### The Architecture

This platform treats governance as an engineering problem. Every rule in the security program is a system invariant: a constraint enforced at the application and schema layer, not documented in a policy PDF.

Core characteristics:

- **20-table relational schema** derived directly from the codified governance specification
- **Multi-phase risk lifecycle** with hard-coded gate enforcement at the API layer
- **Real-time cascade engine** that propagates state changes from controls to risks automatically
- **Framework invariants** enforced in code: no role can bypass them
- **9-role RBAC model** with API-layer permission enforcement
- **Cloud-portable** deployment: containerised services backed by managed PostgreSQL

### Framework Invariants — Enforced in Code, Not Policy

The following invariants are the architectural core. They are enforced at the API layer using gate checks, schema constraints, and scoring engine logic.

| ID | Rule | Enforcement Point |
|---|---|---|
| RINV-1 | Residual risk NEVER updated without validated evidence | API validation gate |
| RINV-4 | Acceptance NEVER permanent — always time-bound | DB constraint + expiry flag |
| RINV-5 | Critical risks NEVER accepted — must Mitigate, Transfer, or Avoid | Scoring engine + API validation |
| RINV-6 | Risk readout NEVER skipped for risks rated Moderate or above | Phase gate check |
| RINV-8 | Scoring NEVER begins without all preconditions satisfied | Phase gate — checklist |
| RINV-9 | Planned/partial/unvalidated controls NEVER reduce residual | Scoring engine logic |
| RINV-10 | Every risk MUST have Risk Owner AND Risk Stakeholder | Schema-level constraint |
| RINV-11 | Expired risks ALWAYS escalated — no silent expiry | API + scheduled job |
| RINV-12 | Treatments NEVER at readout without GRC Engineer validation | Workflow gate |
| RINV-13 | Partial treatment selection ALWAYS documented with rationale | API validation |
| TINV-4 | Full mitigation of a threat scenario REQUIRES an active, linked control_deployment | Schema + API validation |
| TINV-5 | Low severity accepted threat scenarios NEVER permanent — always time-bound | API validation gate |

Full invariant catalogue: [Codified Rules](../specification/codified-rules.md)

---

## 2. Entity Relationship Model

### 2.1 Schema Overview

The schema is derived directly from the governance specification. 20 tables across 5 modules:

| Module | Tables | Purpose |
|---|---|---|
| **Risk Management** | risks, risk_controls, risk_treatments, risk_stakeholders | Risk lifecycle, scoring, treatment tracking |
| **Control Management** | control_objectives, control_activities, control_deployments, control_implementations | Control hierarchy, CE assessment, testing |
| **Policy Management** | policies, standards, policy_exceptions, policy_controls | Policy governance, exception management |
| **Asset Register** | assets, systems, digital_assets, asset_control_mapping | Asset hierarchy, CMDB integration, and deployment targeting |
| **Threat Management**| threat_models, threat_components, threat_scenarios, threat_mitigation_links | STRIDE models, threat mitigations, risk register promotion |
| **Platform** | users, roles, audit_log, comments, attachments | RBAC, audit trail, shared infrastructure |

### 2.2 Key Design Decisions

| Decision | Rationale |
|---|---|
| **Join tables carry state** | `risk_controls` stores CE snapshot at assessment time; `risk_treatments` carries validation flags per risk. State at the relationship level, not just the entity level. |
| **CE assessed per deployment** | CE per control per asset, not per control globally. Worst-case CE across deployments feeds scoring (CINV-6). |
| **Shared entity framework** | Comments, attachments, activity log unified across modules via polymorphic references. |
| **Migration-managed schema** | All changes via migration tooling. No manual DDL in production. |

Full schema with CREATE TABLE statements, all FK relationships, and migration strategy: [Data Model](./data-model.md)

### 2.3 Entity Relationship Diagram

```
┌─────────────┐     M:M      ┌──────────────────┐     1:N      ┌──────────────────┐
│   policies  │──────────────│ control_objectives │─────────────│ control_activities │
└─────────────┘              └──────────────────┘              └──────────────────┘
      │ 1:N                          │ M:M                            │ 1:N
      ↓                              ↓                                ↓
┌─────────────┐              ┌──────────────┐              ┌───────────────────┐
│  standards  │              │    risks     │              │control_deployments│
└─────────────┘              └──────────────┘              └───────────────────┘
      │                              │ 1:N                        │ N:1
      │                              ↓                            ↓
┌─────────────┐              ┌──────────────┐              ┌─────────────────┐
│policy_except│              │risk_treatments│              │     assets    │
└─────────────┘              └──────────────┘              └─────────────────┘
```

*Note: This is a simplified view. Full diagram should be generated from your schema tooling.*

---

## 3. Risk Lifecycle State Machine

Every risk traverses a mandatory multi-phase lifecycle. Phase transitions are gated at the API layer, not in UI validation that can be bypassed.

### 3.1 Phase Summary

| Phase | Name | Gate Condition | Blocks If |
|---|---|---|---|
| 1 | **Intake** | Structured risk statement created (Cause / Threat / Vulnerability / Impact) | Statement incomplete or unstructured |
| 2 | **Preconditions** | 5-item checklist fully checked (INV-7) | Any precondition item unchecked |
| 3 | **Inherent Scoring** | Impact and Likelihood scored; Risk Owner and Stakeholder assigned (INV-9) | Fields empty or roles unassigned |
| 4 | **Treatment Alignment** | Treatments linked; GRC Engineer validation complete (INV-11) | No treatments linked or validation incomplete |
| 5 | **Readout** | Risk Owner reviewed and confirmed treatments (INV-5) | Readout not completed for Moderate+ risks |
| 6 | **Evidence and Residual** | 5-item validation gate complete; evidence uploaded (INV-1) | Residual fields remain read-only until gate passes |
| 7 | **Monitoring** | SLA tracking active; acceptance expiry set if applicable (INV-4) | Acceptance without expiry date is blocked |

### 3.2 Gate Enforcement Implementation

Gates are enforced at the API layer using a middleware pattern:

```
# Pseudocode — gate check before phase transition
def transition_risk(risk_id, target_phase):
    risk = get_risk(risk_id)
    gate = PHASE_GATES[target_phase]

    for condition in gate.preconditions:
        if not condition.evaluate(risk):
            raise GateViolation(
                phase=target_phase,
                condition=condition.name,
                message=condition.failure_message
            )

    risk.lifecycle_phase = target_phase
    risk.updated_at = now()
    audit_log.record(risk_id, "phase_transition", target_phase, actor=current_user)
    return risk
```

### 3.3 Residual Scoring Gate (Phase 6 Detail)

The residual scoring gate is the most critical enforcement point. Residual score fields are read-only until all five conditions are met:

1. Mitigations fully implemented
2. Evidence provided (configs, logs, dashboards, audit artefacts)
3. Treatment effectiveness confirmed by Risk Analyst
4. Governance approval documented
5. Risk drift tracked during treatment period

Implementation: residual score fields carry a `locked` flag that is only released by the gate check function. Direct database updates to residual fields are blocked by a database trigger or RLS policy.

---

## 4. Cascade Propagation Engine

The cascade engine is what separates this architecture from a spreadsheet. When a control fails or a CE rating degrades, the effect propagates automatically through every linked risk record.

### 4.1 Cascade Trigger Rules

| Trigger | Condition | Automated Response | SLA to Act |
|---|---|---|---|
| CE degradation | CE rating drops on any deployment | Risk flagged "Control Changed — Re-evaluation Required"; Risk Analyst notified | Critical: 5bd / High: 10bd / Moderate: 20bd / Mod-Low: 30bd |
| Control failure | Control transitions to Failure state | Warning banner on ALL linked risk records; CISO escalation if >15 business days unresolved | Immediate flag; escalation at 15bd |
| Treatment SLA breach | Target date missed, no revised plan | Risk Owner notified; Stakeholder escalated; governance breach logged | Per risk severity band |
| Acceptance expiry | Time-bound acceptance period reached | Risk auto-flagged; escalation to Risk Owner then CISO; no silent expiry (INV-10) | Immediate; re-approval required |
| CE improvement | CE rating improves post-treatment | Risk flagged "Control Improved — Residual Update Eligible"; full validation gate still required | No automatic score update — analyst-triggered |

### 4.2 Cascade Implementation Pattern

```
# Pseudocode — cascade on control status change
def on_control_status_change(control_id, new_status):
    if new_status == "Failure":
        linked_risks = get_risks_linked_to_control(control_id)
        for risk in linked_risks:
            risk.add_warning("CONTROL_FAILURE", control_id)
            risk.residual_score_locked = True
            notify(risk.risk_analyst, "control_failure_cascade", risk, control_id)
            audit_log.record(risk.id, "cascade_control_failure", control_id)

        if business_days_in_failure(control_id) > 15:
            escalate(control_id, level="CISO", reason="control_failure_unresolved_15bd")
```

### 4.3 What Legacy Tools Cannot Do

The cascade engine replaces five manual processes that legacy GRC tools require analysts to perform by hand:

1. **Control failure → risk flag**: Manual in legacy tools. Automatic in this architecture.
2. **CE degradation → re-evaluation trigger**: Not tracked in legacy tools. FK-enforced here.
3. **SLA breach → escalation chain**: Calendar reminders in legacy tools. API-enforced here.
4. **Acceptance expiry → governance flag**: Silent in legacy tools. Auto-escalated here (INV-10).
5. **Cross-entity impact propagation**: Non-existent in legacy tools. Real-time here via FK triggers.

---

## 5. RBAC Model

### 5.1 Role Groups

| Role | Permissions | Restrictions |
|---|---|---|
| **System_Admin** | Full platform configuration; user management; role assignment | Cannot override governance invariants |
| **Risk_Analyst** | Create/edit risks; perform scoring; validate evidence; trigger escalations | Cannot approve acceptance or treatment decisions |
| **Risk_Owner** | Approve treatments; approve acceptance; confirm readout | Cannot edit risk scores directly |
| **GRC_Engineer** | Validate treatment feasibility; manage control mappings; configure automation; manage platform integrations | Cannot unilaterally approve risk acceptance (SEP-5) |
| **Security_SME** | Provide threat context; review control design; advise on treatment architecture | Advisory only; cannot approve treatments or modify risk scores |
| **Treatment_Owner** | Update treatment status; report blockers; request date extensions | Cannot modify risk records |
| **Control_Owner** | Manage control objectives and activities; approve CE assessments | Cannot be Risk_Owner for linked risks (SEP-3) |
| **Control_Operator** | Execute tests; record results; update deployment status | Cannot modify objective-level fields |
| **Auditor** | Read-only access to all records, audit logs, and version history | No write access to any record |

### 5.2 Enforcement

RBAC is enforced at the API layer, not the UI layer. Every API endpoint checks the caller's role against the required permission before processing the request. UI elements are hidden for convenience but security does not depend on UI enforcement.

```
# Pseudocode — API-layer RBAC check
@require_role(["Risk_Analyst", "Risk_Owner"])
def update_risk_score(risk_id, payload):
    ...
```

### 5.3 Authentication

The platform is designed for OIDC integration. Authentication is abstracted behind a provider interface:

- **Development**: Local auth provider with username/password
- **Production**: OIDC provider (e.g. Okta, Azure AD, Cognito) with JWKS validation
- **Role sync**: OIDC group claims mapped to platform role groups

---

## 6. Deployment Architecture

Three deployment paths are supported. The codified specification is portable across all three. The infrastructure is not.

| Path | Model | Lock-in Risk | Detail |
|---|---|---|---|
| **Path 1: Agentic SaaS** | Platform-hosted, credit-based | High (infra is platform-native) | [deployment-saas.md](./deployment-saas.md) |
| **Path 2: Self-Hosted** | Your infrastructure, full control | Low (IaC reproducible) | [deployment-self-hosted.md](./deployment-self-hosted.md) |
| **Path 3: GRC Vendor + AI** | Vendor platform with AI features | High (vendor-native workflows) | [shared-responsibility.md](./shared-responsibility.md) |

Reference self-hosted cost: ~$52-64/month for a low-traffic single-environment deployment. Full cost model and 7-step deployment sequence in [deployment-self-hosted.md](./deployment-self-hosted.md).

Shared responsibility boundary analysis across all three paths: [shared-responsibility.md](./shared-responsibility.md)

---

## 7. Agentic Engineering Method

This platform was built by a practitioner directing an AI execution layer. The architecture, invariants, and data model were designed by a human. The code was generated by an AI agent against that specification.

### 7.1 The Prompt Sequence

The agent was given no freedom to improvise. Each phase was completed and validated before the next was opened.

| Phase | What Was Provided | What Was Blocked |
|---|---|---|
| **1. Schema Validation** | Full relational schema with FK relationships, join table definitions, lifecycle state enumerations | Writing any application logic before schema was locked and validated |
| **2. State Machine Definition** | Multi-phase risk lifecycle with valid/invalid transitions. All governance invariants declared as inviolable. Scoring formulae. | Improvising on business logic or state transition conditions. Any deviation treated as specification violation. |
| **3. Architecture Definition** | Target stack, RBAC model with permission matrix, deployment model with environment variable abstraction | Making infrastructure or framework decisions independently |

### 7.2 Failure Modes and Correction Protocol

Two failure modes were observed during the build. Both were resolved by fixing the specification, not the code.

**Failure 1: Circular Dependency**
The scoring engine and CE calculation each called the other to resolve a value neither had yet computed. **Root cause:** specification did not define computation order. **Fix:** Added explicit rule that CE calculation resolves first and is treated as a fixed input to the scoring engine. Circular dependency patterns between these modules are prohibited.

**Failure 2: Silent Gate Removal**
A state transition check was rewritten by the agent to resolve a frontend rendering conflict. The governance gate was silently removed. The component rendered correctly but the invariant was absent. **Root cause:** specification described the invariant as a lifecycle rule but did not declare it inviolable at the code layer. **Fix:** Updated specification to declare the invariant explicitly inviolable and to state that no frontend rendering requirement can justify removing a governance gate.

### 7.3 The Correction Protocol

1. **Identify the specification gap.** What instruction was absent or ambiguous?
2. **Update the constraint document.** Add the missing rule. Be precise enough that no reasonable interpretation permits the failure mode.
3. **Clear agent context.** Do not patch the existing build. Residual context contaminates the correction.
4. **Rebuild from the updated specification.** Only the affected components.

This is the core skill of agentic engineering. The barrier is not syntax. It is the discipline to treat every failure as a specification gap and fix the specification before rebuilding.

---

## 8. Integration Roadmap

A standalone platform is a new silo. To scale, governance must integrate into the enterprise operational layer.

### 8.1 Messaging Integration (e.g. Slack, Teams)

| Capability | Mechanism | Governance Impact |
|---|---|---|
| Stakeholder attestations | Structured message to Risk Owner at Phase 5 Readout; approval submitted without platform login | Attestation updates lifecycle phase and triggers next gate |
| Exception approvals | Exception requests routed to Policy Owner with justification, compensating controls, expiry | Approved exceptions written to register with expiry tracking |
| Alert triage | SLA breach, control failure, and expiry alerts with triage action buttons | Triage response updates record state and resets SLA |

### 8.2 Ticketing Integration (ITSM)

| Trigger | Action | Governance Outcome |
|---|---|---|
| Treatment approved | Linked epic/ticket auto-created with title, description, target date, GRC reference | Treatment status transitions to In Progress |
| Ticket closed | Webhook updates GRC: treatment → Complete; CE re-assessment scheduled | Risk flagged as eligible for residual update (full gate still required) |
| Ticket blocked | Webhook updates treatment to Blocked; Risk Owner notified; SLA continues | Escalation triggers if block exceeds SLA |
| Date extended | Extension request auto-created; Risk Owner must approve new target | Approved: treatment date updated. Rejected: original SLA in force. |

### 8.3 Resilience Module (Schema Extension)

| New Entity | Captures | Cascade Behaviour |
|---|---|---|
| `business_impact_analyses` | BIA records linked to assets and systems. RTO, RPO, criticality tier, business process dependencies. | BIA data feeds risk impact scoring. RTO/RPO changes trigger risk re-evaluation. |
| `resilience_ratings` | Per-asset resilience state from backup SLA compliance, RTO/RPO adherence, recovery test results. | Failed backup SLA cascades Failure state to asset resilience rating. Linked risks flagged for re-evaluation. |

### 8.4 Why Agentic AI Makes This Tractable

Each integration is a schema extension and a new set of invariants. With the specification-driven method documented in Section 7, each requires: defining new tables and FK relationships, declaring cascade rules as invariants, and directing the agent to build against those constraints.

The core governance engine does not change. The data model extends. The invariants grow. The execution layer generates the new components.

---

*This architecture document is released under CC BY 4.0. Adapt freely with attribution. See [DISCLAIMER.md](../DISCLAIMER.md) for context on origin and scope.*
