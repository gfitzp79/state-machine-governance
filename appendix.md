# Technical Appendix

**The State Machine Model: Regulatory Mapping, Future Domains, and References**

This appendix contains content that supplements the dedicated specification, architecture, and methodology documents. For the core technical detail, navigate directly:

| Topic | Document |
|---|---|
| Codified governance rules | [specification/codified-rules.md](./specification/codified-rules.md) |
| System invariants with enforcement detail | [specification/invariants-catalogue.md](./specification/invariants-catalogue.md) |
| State transitions and phase gates | [specification/state-transitions.md](./specification/state-transitions.md) |
| Scoring engine implementation | [specification/scoring-model.md](./specification/scoring-model.md) |
| 20-table schema with DDL | [architecture/data-model.md](./architecture/data-model.md) |
| Platform overview (lifecycle, cascade, RBAC) | [architecture/reference-architecture.md](./architecture/reference-architecture.md) |
| AI tool lifecycle governance | [architecture/ai-tool-lifecycle.md](./architecture/ai-tool-lifecycle.md) |
| Agentic SaaS deployment | [architecture/deployment-saas.md](./architecture/deployment-saas.md) |
| Self-hosted deployment | [architecture/deployment-self-hosted.md](./architecture/deployment-self-hosted.md) |
| Shared responsibility model | [architecture/shared-responsibility.md](./architecture/shared-responsibility.md) |
| Methodology | [methodology/specification-driven-dev.md](./methodology/specification-driven-dev.md) |
| Prompt cycle and agent optimisation | [methodology/prompt-cycle.md](./methodology/prompt-cycle.md) |
| Platform prompt library | [methodology/platform-prompt-library.md](./methodology/platform-prompt-library.md) |
| Context window management | [methodology/context-management.md](./methodology/context-management.md) |

---

## DORA Regulatory Mapping

Under the Digital Operational Resilience Act, regulated entities must demonstrate integrated ICT risk management.

| DORA Requirement | Article | State Machine Implementation |
|---|---|---|
| Continuous ICT risk monitoring with documented response | Article 9 | Cross-entity FK propagation: issues and findings cascade to risk records. Response enforced by phase gate. |
| Incident management feeds back into risk register | DORA Article 11 | Planned: incident records will carry FK to risk records with a closure gate requiring risk record update. Specification in progress — see [APPENDIX.md#vulnerability-management](./APPENDIX.md#vulnerability-management) for the adjacent pattern. |
| ICT risk management framework maintained and reviewed | Article 6 | Framework codified as machine-readable rule set. Changes trigger re-assessment cascade on all mapped controls and risks. |
| Register of information on ICT third-party service providers | Article 28 | Third-party risk module: schema extension defined, state machine specified. See [Third-Party Risk](#third-party-risk) below. |
| Change management with defined controls | Article 9 | AI Tool Lifecycle: versioning strategy enforced at Build gate. Breaking changes require Pre-Production re-entry before Production promotion. |
| ICT third-party oversight where vendor-hosted | Article 28 | AI Tool Lifecycle: Pre-Production gate confirms shared responsibility boundary before any user onboarding. |

For firms operating under the Central Bank of Ireland's accountability framework, these are mandatory demonstrable requirements. The cascading state machine architecture is the direct structural implementation of what DORA requires.

---

## EU AI Act Mapping

For organisations operating AI systems in scope under the EU AI Act, the lifecycle model provides a governance structure that maps to the technical documentation and lifecycle management requirements.

| EU AI Act Requirement | Article | Lifecycle Implementation |
|---|---|---|
| Technical documentation for high-risk AI systems | Article 11 | Ideation through Deprecation artefacts: ownership record, security document, architecture decision record, runbook, and disposal plan |
| Logging and record-keeping obligations | Article 12 | Pre-Production gate: prompt observability pipeline and SIEM integration required before Production. Prompt telemetry treated as audit-grade logging. |
| Human oversight requirements | Article 14 | Build gate: AI-specific code review policy (dual-review or human-in-the-loop) required for critical paths |
| Post-market monitoring | Article 72 | Production phase: quarterly ownership review, weekly prompt anomaly review, monthly dependency review |
| Decommissioning and data disposal | Article 18 | Deprecated phase: data retention and disposal plan, documentation archive, and final security review required before decommission |

These mappings represent the author's interpretation of publicly available regulatory text. They do not constitute legal or compliance advice.

---

## Vulnerability Management

Five enforced state transitions.

```
Discovery --> Verified --> Remediation --> Remediated --> Verified Closed
                |
                +--> Accepted (time-bound, risk owner sign-off required)
```

**State definitions:**

- **Discovery:** Scan finding ingested. Severity scored. Assigned to remediation owner via FK to asset and team records.
- **Verified:** AppSec or GRC Engineer confirms the finding is a genuine vulnerability, not a false positive. Duplicate check against open vulnerability register.
- **Remediation:** Active work in progress. SLA clock running. Linked to internal ticket via FK. Overdue findings propagate to linked risk record.
- **Remediated:** Fix applied and evidenced. Awaiting verification scan or manual confirmation.
- **Verified Closed:** Closure confirmed by independent review. Linked risk record updated. Exposure trend adjusted.
- **Accepted:** Time-bound exception. Risk owner sign-off required. Expiry date enforced. Auto-reopens on expiry.

**Invariants:**

- A finding cannot move to Verified Closed without an independent reviewer distinct from the remediation owner.
- An Accepted exception requires a named risk owner, a time-bound expiry date, and a linked risk record. Acceptance without all three is rejected at the schema layer.
- Overdue findings in Remediation automatically cascade to linked risk records and freeze residual scoring until resolved.

**Integration points:** Scanning tool output (CSV or API) ingested at Discovery. Internal ticketing system linked at Remediation via FK. SIEM alert on SLA breach. Executive dashboard exposure trend updated at Verified Closed.

Specification in progress.

---

## Resilience

BIA, RPO, and RTO as enforced state variables, linked to the risk register via FK.

**Problem statement:** Resilience requirements (RPO, RTO) are typically documented in BIA spreadsheets and business continuity plans that are disconnected from the live risk register. When a risk materialises and an asset is unavailable, the organisation has to locate the relevant BIA document to understand the recovery obligation. The governance gap is structural.

**Architecture:** Each critical asset carries enforced RPO and RTO values as schema-level constraints. Asset state changes propagate to linked risk records. If a risk affecting a critical asset moves to active, the recovery obligation is surfaced immediately via FK, not retrieved from a document.

**State machine:** Business Impact Assessment phases govern the lifecycle of resilience requirements from identification through annual review.

```
Identification --> Impact Analysis --> Recovery Definition --> Approved --> Annual Review
                                                                  |
                                                                  +--> Triggered (incident active)
```

**Invariants:**

- An asset classified as critical cannot have a null RPO or RTO. The schema rejects the write.
- A risk linked to a critical asset cannot move to residual scoring without confirmed recovery controls mapped to that asset's RPO and RTO.
- Annual Review is time-enforced: assets that have not completed review within 12 months are flagged in the executive dashboard and the associated risks are frozen at their last verified score.

Specification in progress.

---

## Third-Party Risk

Schema extension defined. State machine specified. Integration with the core risk register via FK.

Third-party risk records carry the vendor entity, the services in scope, the criticality classification, and the contractual and technical controls. State transitions enforce assessment cadence: vendors above a defined criticality threshold cannot remain in the Assessed state beyond the agreed review cycle without triggering a cascade to linked risk records.

DORA Article 28 register requirements are satisfied by the vendor record schema: register of ICT third-party service providers, service descriptions, criticality classification, and assessment dates.

Full specification planned as a dedicated architecture document.
