# SaaS Exit Governance

**Document type:** Architecture
**Status:** Specification
**Depends on:** `architecture/ai-tool-lifecycle.md`, `architecture/shared-responsibility.md`
**Referenced by:** `architecture/reference-architecture.md`, `APPENDIX.md`

---

## Purpose

This document specifies the governance requirements for transitioning from a SaaS vendor tool to an internally built replacement. It covers the parallel-run period, data migration, compliance obligation transfer, user transition, and vendor contract wind-down.

The motivation is operational. When an organisation replaces a SaaS tool with an internally built alternative, three categories of risk converge simultaneously: the new tool must satisfy the compliance obligations the vendor previously attested to; historical data must be migrated without loss of integrity or audit trail; and the organisation must operate both systems in parallel until the internal build is validated in production. None of these are addressed by the AI Tool Lifecycle alone. The lifecycle governs what you build. This document governs what you leave.

---

## Scope

This specification applies when an internally built AI tool is intended to replace a SaaS vendor tool that is currently in production use. It does not apply to: net-new tools that have no SaaS predecessor, SaaS tools being replaced by a different SaaS vendor (vendor-to-vendor migration), or SaaS tools being decommissioned without replacement.

---

## Exit State Machine

The SaaS exit process follows a five-phase state machine. Each phase has gate conditions. A tool cannot advance unless all gate conditions are satisfied.

```
Assessment --> Parallel Run --> Validation --> Cutover --> Vendor Wind-Down
                  |                                            ^
                  +---> [validation fails] --> Assessment ----->+
```

Phase regression is permitted. If validation fails during the Parallel Run, the process returns to Assessment with a documented reason. The SaaS tool remains the system of record throughout any regression.

---

## Phase Definitions

### Phase 1: Assessment

**Purpose:** Confirm that the internal build can satisfy the obligations currently met by the SaaS vendor before any migration work begins.

**Entry condition:** The internal replacement tool has reached Production status in the AI Tool Lifecycle (Phase 4 of `ai-tool-lifecycle.md`).

**Required artefacts before advancing:**

| Artefact | Owner | Notes |
|---|---|---|
| Compliance obligation inventory | GRC function | List every compliance requirement the SaaS vendor currently satisfies: certifications relied upon (SOC 2, ISO 27001), contractual commitments to customers that reference vendor attestations, regulatory requirements met via vendor controls |
| Coverage gap analysis | GRC function | For each compliance obligation, document whether the internal build satisfies it directly, requires a compensating control, or creates a gap that must be accepted |
| Data migration plan | Ownership team | What data moves, what format, what validation confirms integrity, what audit trail is preserved |
| Parallel run plan | Ownership team | Duration, acceptance criteria for declaring the internal build production-ready, rollback trigger conditions |
| Customer and stakeholder notification plan | Legal and commercial | If customers were told their data is processed by the SaaS vendor, what notification is required when processing moves in-house |
| Contract review | Legal and procurement | Notice periods, data return clauses, early termination penalties, data deletion confirmation requirements |

**Gate condition to advance:** All compliance obligations inventoried. Coverage gap analysis complete with no unaccepted gaps above the agreed risk threshold. Data migration plan approved by the data owner. Contract review complete with exit timeline confirmed.

**Invariant:** A SaaS exit cannot proceed if any compliance obligation currently met by the vendor will become unmet after cutover and no compensating control or risk acceptance has been documented. The obligation does not disappear because the vendor does. It transfers.

---

### Phase 2: Parallel Run

**Purpose:** Operate the internal build alongside the SaaS tool for a defined period, with the SaaS tool remaining the system of record until the internal build is validated.

**Entry condition:** All Phase 1 gate conditions met.

**Operating rules during parallel run:**

| Rule | Detail |
|---|---|
| System of record | The SaaS tool remains the system of record. All official outputs, reports, and attestations reference the SaaS tool during this period. |
| Data synchronisation | If both systems process live data, define the synchronisation direction. One-way (SaaS to internal) is the safest default. Bi-directional sync requires conflict resolution rules defined before the parallel run starts. |
| User scope | Define which users operate on the internal build during the parallel run. Full user migration before validation is a risk. Start with the ownership team and expand. |
| Incident handling | Incidents on the internal build during the parallel run are handled under the internal build's incident response plan. The SaaS tool's support model remains active. |
| Duration | Minimum parallel run duration must be defined in the parallel run plan. It should cover at least one full operational cycle (e.g., one audit cycle, one reporting period, one quarterly review). |

**Acceptance criteria (all required to advance):**

| Criterion | Validation method |
|---|---|
| Data integrity confirmed | Reconciliation between SaaS export and internal build import. Row counts, FK integrity, hash comparisons on critical records. |
| Functional parity confirmed | Every workflow that operated on the SaaS tool has been executed on the internal build with equivalent or better outcomes. |
| Compliance coverage confirmed | Every obligation in the compliance obligation inventory is demonstrably met by the internal build or an accepted compensating control. |
| User acceptance confirmed | Users who operated on the internal build during the parallel run confirm it meets operational requirements. |
| Monitoring confirmed | Prompt telemetry, application logging, and SIEM integration are confirmed active and generating expected alert volumes. |

**Gate condition to advance:** All acceptance criteria met. Ownership team signs off. GRC function confirms compliance coverage. Rollback trigger conditions were not met during the parallel run.

**Invariant:** The SaaS tool remains the system of record until validation is explicitly confirmed. There is no implicit cutover. If the parallel run ends without explicit sign-off, the SaaS tool remains the system of record and the parallel run extends.

---

### Phase 3: Validation

**Purpose:** Formal confirmation that the internal build satisfies all requirements for becoming the system of record.

**Entry condition:** All Phase 2 gate conditions met.

**Required artefacts before advancing:**

| Artefact | Owner | Notes |
|---|---|---|
| Validation report | Ownership team | Documents each acceptance criterion from Phase 2, evidence of satisfaction, any exceptions |
| Updated compliance register | GRC function | Reflects the internal build as the control source for all previously vendor-met obligations |
| Updated risk register | GRC function | Any new risks introduced by the transition (key person risk, reduced SLA, loss of vendor support) documented and scored |
| Customer notification confirmation | Legal and commercial | If notification was required, confirmation it was sent with the required notice period |
| Rollback plan | Ownership team | If cutover fails, how to revert to the SaaS tool within a defined recovery window |

**Gate condition to advance:** Validation report approved by the sponsoring function. Compliance register updated. Rollback plan documented and tested.

---

### Phase 4: Cutover

**Purpose:** Transfer the system of record from the SaaS tool to the internal build.

**Entry condition:** All Phase 3 gate conditions met.

**Cutover sequence:**

1. Final data export from SaaS tool (full backup with verified integrity).
2. Internal build designated as system of record. All official outputs reference the internal build from this point.
3. SaaS tool access restricted to read-only for the defined archival period.
4. Users migrated to internal build. SaaS tool credentials revoked after the archival period.

**Rollback window:** A defined period (minimum 30 days recommended) during which the SaaS tool can be reinstated as the system of record if a critical deficiency is discovered. The rollback plan from Phase 3 defines the procedure.

**Gate condition to advance:** Cutover complete. Internal build operating as system of record for the defined stabilisation period (minimum one operational cycle). No rollback triggers activated.

---

### Phase 5: Vendor Wind-Down

**Purpose:** Govern the structured exit from the SaaS vendor relationship.

**Entry condition:** Cutover stabilisation period complete. No rollback triggers activated.

**Required artefacts before closure:**

| Artefact | Owner | Notes |
|---|---|---|
| Data return or deletion confirmation | Vendor (requested by legal) | Written confirmation from the vendor that all customer data has been returned or destroyed per contract terms |
| Contract termination confirmation | Legal and procurement | Formal termination of the vendor agreement, with confirmation of any surviving obligations (indemnities, audit rights) |
| Final SaaS cost reconciliation | Finance | Confirmation of final invoice, any early termination penalties, and cost savings projection from the transition |
| Vendor assessment archive | GRC function | Archive the vendor's last assessment, certifications, and any due diligence documentation. These may be needed for future audit queries about the historical period when the vendor was in use. |
| Lessons learned | Ownership team | What worked, what did not, what would change in the next SaaS exit. Feeds back into the parallel run plan template for future transitions. |

**Terminal state:** Vendor Wind-Down is a terminal state for the SaaS relationship. The internal build continues to be governed under the AI Tool Lifecycle (Production or Maintenance phase).

---

## Data Migration Governance

Data migration during a SaaS exit is not a technical task with a governance wrapper. It is a governance task with a technical execution.

**Integrity requirements:**

- Row count reconciliation: source export count must match destination import count for every entity type. Discrepancies are investigated before the parallel run advances.
- FK integrity: all foreign key relationships must be preserved. If the SaaS tool's export format uses different identifiers, a mapping table is created and validated.
- Audit trail continuity: historical records must carry their original timestamps, creators, and state transitions. The internal build must not overwrite historical metadata with import-time values.
- Hash validation: for critical record types (risk assessments, control test results, audit evidence), a hash comparison confirms content integrity between source and destination.

**Data that does not migrate:**

- Vendor-specific metadata (internal vendor IDs, platform-specific fields with no equivalent in the internal build)
- Session data, cached computations, and transient state
- Data covered by vendor data processing agreements that prohibit transfer to non-vendor systems

**Retention of SaaS data post-cutover:** The final SaaS export must be retained in a governed archive for the period required by applicable regulation or contractual obligation. This is not optional. If the SaaS vendor deletes customer data upon contract termination (as most do), the final export is the only surviving record of the historical period.

---

## Compliance Obligation Transfer

The compliance obligation transfer is the highest-risk element of a SaaS exit. Most organisations underestimate this because the vendor's compliance posture was invisible during normal operations.

**Categories of obligation:**

| Category | Example | Transfer requirement |
|---|---|---|
| Certifications relied upon | Vendor's SOC 2 Type II report referenced in customer contracts or RFPs | Internal build must either obtain equivalent certification or customer contracts must be amended to reflect the new control environment |
| Regulatory controls | Vendor provided encryption at rest, access logging, data residency guarantees required by DORA, GDPR, or sector regulation | Internal build must implement equivalent controls and demonstrate compliance independently |
| Contractual SLAs | Vendor committed to 99.9% uptime, 4-hour incident response, 72-hour data breach notification | Internal build must define and commit to equivalent SLAs. If SLAs are reduced, customers must be notified. |
| Audit rights | Vendor contracts included audit rights or penetration testing provisions | Internal build's hosting environment must support equivalent audit access |
| Insurance coverage | Vendor carried cyber insurance that provided indirect coverage for data processing | Internal build's hosting environment (self-hosted or agentic SaaS) must be assessed against the organisation's own insurance policy |

**Invariant:** No compliance obligation met by the SaaS vendor is considered "retired" by the act of leaving the vendor. Every obligation must be explicitly mapped to an internal control, a compensating control, or a documented risk acceptance with time-bound expiry.

---

## Relationship to Other Documents

| Topic | Document | Relationship |
|---|---|---|
| Lifecycle governance for the internal build | `architecture/ai-tool-lifecycle.md` | The internal build must be in Production (Phase 4) before a SaaS exit can enter Assessment |
| Shared responsibility for the internal build | `architecture/shared-responsibility.md` | The shared responsibility boundary for the internal build must be defined before the parallel run starts |
| Deployment architecture | `architecture/deployment-saas.md`, `architecture/deployment-self-hosted.md` | The deployment path determines which infrastructure-layer obligations transfer to the internal team |

---

## Regulatory Alignment

| Requirement | Regulation | Exit Governance Implementation |
|---|---|---|
| ICT third-party exit strategy | DORA Article 28(8) | Five-phase exit state machine with defined gate conditions and rollback provisions |
| Data portability and return | DORA Article 28(7) | Data migration governance: integrity validation, audit trail continuity, vendor deletion confirmation |
| Continuity of ICT services during transition | DORA Article 28(8) | Parallel run with SaaS as system of record until validation complete |
| Data processing agreement termination | GDPR Article 28(3)(g) | Vendor Wind-Down: data return or deletion confirmation required before contract closure |
| Record retention obligations | Sector-specific | Final SaaS export retained in governed archive for the applicable retention period |

---

*This specification is released under CC BY 4.0. Adapt freely with attribution.*
