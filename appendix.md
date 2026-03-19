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
| Incident management feeds back into risk register | Article 11 | Incident records carry FK to risk records. Incident closure gate requires risk record update. |
| ICT risk management framework maintained and reviewed | Article 6 | Framework codified as machine-readable rule set. Changes trigger re-assessment cascade on all mapped controls and risks. |
| Register of information on ICT third-party service providers | Article 28 | Third-party risk module: schema extension defined, state machine specified. See [Third-Party Risk](#third-party-risk) below. |

For firms operating under the Central Bank of Ireland's accountability framework, these are mandatory demonstrable requirements. The cascading state machine architecture is the direct structural implementation of what DORA requires.

---

## Vulnerability Management

Five enforced state transitions. Current tooling treats these as loosely linked records.

| Transition | Gate Requirement | Enforcement |
|---|---|---|
| **Discovered → Triaged** | Asset criticality AND exploitability context (EPSS, not just CVSS). Medium severity with active exploitation warrants critical SLA. | Gate rejects without both. |
| **Triaged → Assigned** | Confirmed owner as FK. SLA clock starts here, not at discovery. | No owner, no advance. |
| **Assigned → In Remediation** | Linked ITSM ticket ID as verifiable reference. | No ticket, no transition. |
| **In Remediation → Verified Closed** | Re-scan confirmation. Manual status update does not satisfy. | Automated verification or gate holds. |
| **Any → Exception/Accepted** | Time-bound expiry AND named approver at correct authority level. | No expiry, no save. NOT NULL on both. |

A critical VM finding on a system underpinning a risk record triggers automatic re-evaluation of the linked risk's residual score. Finding and risk records connected via FK. Finding cannot close without confirmed impact assessment on linked risks.

---

## Resilience

BIA/RPO/RTO as enforced state variables, not standalone spreadsheets.

| Integration | Mechanism | Enforcement |
|---|---|---|
| **Asset Register → Resilience** | New assets feed BIA, RPO, RTO assignment automatically. | Asset without resilience classification cannot be marked production-ready. |
| **Resilience → SIEM** | RPO/RTO exposed as live variables consumed by SIEM runbooks. | Recovery objective changes → SecOps KPIs adjust dynamically. |
| **Resilience → Risk Register** | BIA outcomes inform risk scoring. Critical service with unmet RTO becomes a risk record. | FK link, not manual update. |
| **VM Critical Finding → Resilience** | CVE above severity on critical asset triggers automatic resilience review. | Finding cannot close without BIA impact assessment. VM and resilience records linked as FK. Neither closes without the other. |

---

## Third-Party Risk

**Status: Roadmap — schema extension defined, not yet built.**

Third-party risk management follows the same state machine architecture as internal risk governance. The governance logic is already codified in [specification/codified-rules.md](./specification/codified-rules.md). The schema extension required is documented below. The methodology is identical to the core build.

### Scope

Vendor risk assessments, supply chain risk, concentration risk, and DORA Article 28 register of information on ICT third-party service providers.

### Schema Extension

| New Entity | Captures | FK Relationships |
|---|---|---|
| `vendor_risk_assessments` | Third-party vendor risk normalised into the same lifecycle as internal risks. Vendor name, contract ref, criticality tier, assessment date, inherent score, residual score, treatment decision. | FK → risks (promoted findings), FK → assets (vendor-managed assets), FK → control_deployments (vendor-managed controls) |
| `vendors` | Vendor registry: name, category, criticality, contract expiry, primary contact, assessment owner. | Parent of vendor_risk_assessments |
| `vendor_contracts` | Contract terms, renewal dates, exit clauses, SLA commitments, data processing terms. | FK → vendors |
| `concentration_risk_links` | Many-to-many: vendors ↔ business processes. Enables concentration risk analysis. | FK → vendors, FK → assets (representing business processes) |

### State Machine

Vendor risk assessments traverse the same 7-phase lifecycle as internal risks. The only additions:

| Phase | Vendor-Specific Gate Condition |
|---|---|
| Phase 1 (Intake) | Vendor criticality tier assigned (Tier 1/2/3). DORA Article 28 register entry created. |
| Phase 3 (Scoring) | Inherent score includes supply chain concentration factor. |
| Phase 7 (Monitoring) | Monitoring cadence aligned to vendor criticality: Tier 1 quarterly, Tier 2 semi-annually, Tier 3 annually. |

### Cascade Behaviour

| Trigger | Cascade |
|---|---|
| Vendor SLA breach | Triggers same escalation path as internal control failure. Risk Owner notified. |
| Vendor contract expiry approaching | Auto-flag 90 days before expiry. Assessment renewal required. |
| Vendor finding promoted to risk register | Bidirectional FK maintained between vendor assessment and internal risk record. |
| Concentration risk threshold exceeded | Flag when >X% of critical business processes depend on a single vendor. Threshold configurable. |

### DORA Article 28 Alignment

The vendor_risk_assessments table, when populated with the fields required by DORA Article 28, constitutes the Register of Information on ICT third-party service providers. The platform's lifecycle enforcement ensures the register is maintained, not just created.

### Build Sequence (When Scheduled)

```
1. vendors table + CRUD
2. vendor_contracts table + FK
3. vendor_risk_assessments table + RLS
4. concentration_risk_links junction table
5. Extend risk lifecycle to accept vendor_assessment_id as intake source
6. Phase gate modifications (vendor-specific preconditions)
7. Cascade rules (vendor SLA breach → risk flag)
8. DORA Article 28 export view
```

---

## References

| Framework / Standard | Relevance |
|---|---|
| **NIST SP 800-207** — Zero Trust Architecture | Agent identity: continuous auth for all entities |
| **NIST Cybersecurity Framework (CSF)** | Risk management lifecycle mapping |
| **NIST RMF** | Organisational risk tiering (Tier 1-4) |
| **DORA** — Digital Operational Resilience Act | Articles 6, 9, 11, 28: integrated ICT risk management |
| **Central Bank of Ireland** — PCF Accountability | Mandatory demonstrable requirements for integrated risk management |
| **OWASP Agentic Security** | Excessive agency prevention, agent permission scoping |
| **OWASP State of Agentic AI Security 1.0** (Jul 2025) | Agentic security landscape assessment |
| **IMDA Model AI Governance for Agentic AI** (Jan 2026) | Governance for multi-agent systems in regulated environments |
| **WEF AI Agents in Action** (Nov 2025) | Enterprise deployment patterns |
| **FAIR Risk Methodology** | Quantitative risk scoring applicable to scoring module |
| **ISO 27005** | Risk management process alignment |
| **SOC 2 / COSO** | Control framework and trust services criteria |

---

*All content developed independently. See [DISCLAIMER.md](./DISCLAIMER.md).*
