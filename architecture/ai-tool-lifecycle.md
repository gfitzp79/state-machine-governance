# AI Tool Lifecycle Governance

**Document type:** Architecture  
**Status:** Specification  
**Depends on:** `architecture/deployment-saas.md`, `architecture/deployment-self-hosted.md`, `architecture/shared-responsibility.md`  
**Referenced by:** `architecture/reference-architecture.md`, `APPENDIX.md`

---

## Purpose

This document specifies the lifecycle state machine for internally built AI tools. It defines the phases, gate conditions, ownership requirements, and terminal state criteria that govern an AI tool from ideation through decommissioning.

The motivation is structural. When an organisation moves from SaaS consumption to internally built AI tools, the operational responsibilities previously abstracted by the vendor transfer in full to the internal team. SDLC discipline, security, support, monitoring, and lifecycle management must be explicitly governed. Without a defined lifecycle model, these responsibilities are not absorbed. They accumulate as undeclared debt.

This specification defines the state machine that governs that transfer of accountability.

---

## Scope

This lifecycle model applies to any AI tool built and operated internally, including:

- Agentic applications built on SaaS platforms (Lovable, Replit, or equivalent)
- Self-hosted deployments on internal or cloud infrastructure
- Hybrid builds where the specification originates internally but the runtime is vendor-hosted

It does not apply to SaaS tools where the organisation is a consumer, not an operator.

---

## Lifecycle State Machine

An AI tool transitions through six defined phases. Each phase has named entry conditions, required artefacts, governance responsibilities, and exit gate conditions. A tool cannot advance to the next phase unless all gate conditions are satisfied.

```
Ideation --> Build --> Pre-Production --> Production --> Maintenance --> Deprecated
                           |                                                  ^
                           +----> [kill criteria met] ---------------------->+
```

Phase regression is permitted. A tool in Production may be moved back to Pre-Production if a production incident reveals an unresolved architectural defect. The regression is a gate decision, not an exception. It must be logged in the tool's ownership record with a stated re-promotion criterion.

---

## Phase Definitions

### Phase 1: Ideation

**Purpose:** Establish that the build is justified and owned before a single prompt is written.

**Entry condition:** A sponsor or team has identified a governance or operational gap that an internal AI tool would address.

**Required artefacts before advancing:**

| Artefact | Owner | Notes |
|---|---|---|
| Problem statement | Requesting team | One paragraph. What breaks without this tool? |
| Ownership assignment | Named individual or team | Accountable for full lifecycle, not delivery only |
| Build vs buy assessment | Ownership team | Why internal build is warranted |
| Data classification | Security function | What data will this tool create, process, or store |
| Dependency on existing governance systems | Ownership team | FK relationships or data flows to other internal systems |

**Gate condition to advance:** Ownership assignment confirmed in writing. Problem statement approved by the sponsoring function. Data classification complete.

**Invariant:** A tool cannot advance from Ideation without a named owner. Ownership cannot be assigned to a role. It must be assigned to a named individual or a named team with a designated lead.

---

### Phase 2: Build

**Purpose:** Produce a working implementation against a validated specification.

**Entry condition:** All Phase 1 gate conditions met.

**Required artefacts before advancing:**

| Artefact | Owner | Notes |
|---|---|---|
| Specification package | Building practitioner | Data model, state machine, invariants, acceptance criteria |
| Architecture decision record | Building practitioner | Tech stack, deployment target, auth model |
| Security document | Security function | Threat model, access control design, prompt boundary definitions |
| Versioning strategy | Ownership team | v0.x for pre-production, v1.0 for first production release, v1.x for patches, v2.0 for breaking changes |
| AI-specific code review policy | Security function | Dual-review or human-in-the-loop policy for critical paths |

**Gate condition to advance:** Specification package complete. Security document signed off. Versioning strategy documented. No open critical findings from pre-build threat model.

**Invariant:** The specification is the asset. Generated code is an output of the specification, not a substitute for it. If code diverges from the specification, the specification is corrected and the code is rebuilt. The specification is not modified to match broken code.

---

### Phase 3: Pre-Production

**Purpose:** Validate the implementation against production-equivalent conditions before any live data or operational use.

**Entry condition:** All Phase 2 gate conditions met. Version tag v0.x applied.

**Required artefacts before advancing:**

| Artefact | Owner | Notes |
|---|---|---|
| Production readiness checklist | Ownership team | See below |
| Runbook | Ownership team | Operating procedures, restart paths, escalation |
| Incident response plan | Security function | AI-specific: includes prompt anomaly response |
| Prompt observability configuration | Engineering or security function | Logging, alerting thresholds, SIEM integration |
| SIEM integration confirmation | Security function | Prompt telemetry flowing into monitoring pipeline |
| Penetration test or AppSec review | Security function | AI-generated code is in scope. Not optional. |
| Support model definition | Ownership team | On-call rotation, escalation paths, SLA commitments |
| Capacity planning record | Ownership team | % of team time allocated to maintenance post-launch |

**Production readiness checklist (all items required):**

- [ ] Secure SDLC compliance confirmed
- [ ] Versioning strategy applied: build tagged at v0.x
- [ ] Architecture documentation current and accurate
- [ ] Runbook complete and accessible to all named on-call individuals
- [ ] Monitoring active: application logs, error rates, latency
- [ ] Prompt telemetry active: input/output logging with anomaly thresholds defined
- [ ] SIEM integration live: prompt telemetry in monitoring pipeline
- [ ] Incident response plan covers AI-specific failure modes
- [ ] Support model documented: escalation path from end user to owner
- [ ] Maintenance capacity allocated: named % of team time reserved post-launch

**Gate condition to advance:** All checklist items complete. Penetration test findings resolved to agreed residual. SIEM integration confirmed live. Capacity allocation documented and accepted by the sponsoring function.

**Invariant:** A tool cannot enter Production without confirmed prompt observability and SIEM integration. Prompt logs are a detection surface and must be treated with the same rigor as application logs. The absence of prompt telemetry is an unacceptable security gap, not a deferred enhancement.

---

### Phase 4: Production

**Purpose:** Operate the tool as a managed internal system with defined ownership, monitoring, and change governance.

**Entry condition:** All Phase 3 gate conditions met. Version bumped to v1.0.

**Ongoing governance requirements:**

| Requirement | Cadence | Owner |
|---|---|---|
| Ownership review | Quarterly | Sponsoring function |
| Prompt anomaly review | Weekly minimum | Security function |
| Dependency review (model versions, platform dependencies) | Monthly | Ownership team |
| Security patch assessment | Per CVE notification | Ownership team |
| Specification currency check | Per change | Building practitioner |
| Capacity utilisation review | Quarterly | Ownership team |

**Change governance:** All changes to production tools follow the versioning strategy. Patches increment v1.x. Breaking changes require re-entry to Pre-Production at v1.x-rc before promotion to v2.0. Emergency patches are permitted with post-deployment specification update within 48 hours.

**Invariant:** The ownership assignment confirmed in Phase 1 remains active and named. If the owner changes role or leaves the organisation, a successor must be named before the vacancy is created, not after. Undocumented or unowned production tools are a governance finding, not an operational inconvenience.

---

### Phase 5: Maintenance

**Purpose:** Sustain an in-production tool whose active development has ceased but which remains operational.

**Entry condition:** The tool is in Production and the ownership team has formally declared that no further feature development is planned. The tool is operating within defined parameters.

**Distinction from Production:** In Maintenance, no new features are built. Security patches, dependency updates, and critical bug fixes continue. The tool remains governed but is not a development priority.

**Governance requirements:**

| Requirement | Cadence | Owner |
|---|---|---|
| Kill criteria assessment | Quarterly | Sponsoring function |
| Security patch assessment | Per CVE notification | Ownership team |
| Dependency currency check | Monthly | Ownership team |
| Usage review | Quarterly | Ownership team |

**Kill criteria assessment:** At each quarterly review, the sponsoring function assesses whether the tool meets any kill criterion (see Phase 6). If one or more criteria are met, the tool is promoted to Deprecated.

---

### Phase 6: Deprecated

**Purpose:** Govern the structured decommissioning of a tool that has met one or more kill criteria.

**Kill criteria (any one sufficient to initiate deprecation):**

| Criterion | Definition |
|---|---|
| Business function absorbed | The need the tool addressed is now met by another internal system or vendor platform |
| Owner vacancy unresolved | The named owner has left and no successor has been confirmed within 30 days |
| Security debt unresolvable | Outstanding security findings cannot be remediated within an agreed timeline and risk cannot be accepted |
| Usage below threshold | Active user count has fallen below the minimum defined at capacity planning for two consecutive quarters |
| Dependency end-of-life | A core dependency (model version, hosting platform, auth provider) has reached end-of-life with no viable upgrade path |
| Specification currency lost | The specification no longer accurately represents the system in production and cannot be restored within an agreed timeline |

**Deprecation artefacts (all required before decommission):**

| Artefact | Owner | Notes |
|---|---|---|
| Data retention and disposal plan | Security and legal | Where does the data go? What is destroyed? |
| User migration plan | Ownership team | What replaces this tool for current users? |
| Documentation archive | Ownership team | Specification, architecture, and runbook archived, not deleted |
| Kill criterion record | Sponsoring function | Which criterion triggered deprecation and on what date |
| Final security review | Security function | Confirm no residual data exposure post-decommission |

**Terminal state:** Deprecated is a terminal state. A deprecated tool cannot be promoted back to Production. If the business case re-emerges, it constitutes a new Ideation phase. The archived documentation from the deprecated tool may be used as input to the new specification, but it does not replace it.

---

## Key Person Risk

An internally built AI tool carries inherent key person risk if knowledge of its architecture, configuration, or operating model is held by a single individual and is not externally documented.

Key person risk becomes a governance finding when:

- The runbook cannot be executed by any named on-call individual other than the original builder
- The specification is not current and the builder is the only person who can reconstruct it
- The prompt library or agent configuration exists only on the builder's local environment

Key person risk must be assessed at the Phase 3 gate and reviewed quarterly during Production and Maintenance.

---

## Relationship to Shared Responsibility

This lifecycle model extends the shared responsibility model defined in `architecture/shared-responsibility.md`. That document establishes the boundary between what the hosting platform secures and what the internal team owns. This document governs the internal team's side of that boundary across the full tool lifecycle.

The shared responsibility model answers: what is yours to own?

This lifecycle model answers: how do you own it, from the first prompt to the final decommission?

---

## Regulatory Alignment

| Requirement | Regulation | Lifecycle Enforcement |
|---|---|---|
| ICT risk management across full technology lifecycle | DORA Article 6 | Phase gates enforce governance at each transition. Deprecation requires documented disposal. |
| Change management with defined controls | DORA Article 9 | Change governance in Phase 4: versioning strategy, pre-production re-entry for breaking changes |
| ICT third-party oversight where vendor-hosted | DORA Article 28 | Phase 3 gate confirms shared responsibility boundary before production |
| AI system lifecycle documentation | EU AI Act Article 18 | Ideation through Deprecation artefacts satisfy technical documentation requirements for applicable systems |

---

## Cross-References

| Topic | Document |
|---|---|
| Deployment on agentic SaaS platforms | `architecture/deployment-saas.md` |
| Self-hosted deployment architecture | `architecture/deployment-self-hosted.md` |
| Shared responsibility model | `architecture/shared-responsibility.md` |
| Agent identity and scope-bounded permissions | `architecture/reference-architecture.md` |
| Specification-driven development methodology | `methodology/specification-driven-dev.md` |
| Prompt cycle and context management | `methodology/prompt-cycle.md` |
