# The State Machine Model

**A Reference Architecture for Specification-Driven Security Tooling Built with Agentic AI**

---
> **Framework & IP Disclaimer:** This repository represents independent research. All data models, state transitions, and system invariants are strictly based on generic, public-domain industry frameworks (NIST SP 800-30, ISO 27005, FAIR). This codebase does not contain, reflect, or represent proprietary intellectual property, internal product roadmaps, or specific use-cases of any current or former employer. Read the full [DISCLAIMER.md](./DISCLAIMER.md).
---

## What This Is

A reference architecture and methodology for building security tooling that enforces state machine logic natively, using specification-driven agentic AI development. The reference implementation is a GRC platform. The methodology applies to any security domain where the gap between policy intent and tool enforcement is wide.

Codified governance rules, data models, deployment architecture, the complete methodology to build from them, and a lifecycle model that governs the tools themselves from ideation through decommissioning.

## Why It Exists

Enterprise security and GRC tooling is typically designed around a vendor's model of how governance should work. Teams configure their frameworks to fit the platform, not the other way around. The right architecture inverts this: tooling that conforms to your framework, your rules, your operating model. When teams can specify and build precisely, the quality bar for what a vendor platform must offer also rises.

Teams with precise specifications can now build exact implementations of their security and governance frameworks in weeks using agentic AI, rather than months of vendor configuration.

The same capability that makes internal builds fast also removes the operational buffer SaaS vendors provided silently: SDLC discipline, AppSec testing, versioning, monitoring infrastructure, support models, and incident response. When you build internally, every one of those responsibilities transfers to you in full on the day the first user is onboarded. The lifecycle model in this repository governs that transfer.

## Core Thesis

- **Governance is a state machine, not a spreadsheet.** Risks, controls, issues, and policies are interconnected entities whose state changes propagate across the system.
- **Precise specifications enforce what can happen, not just what should happen.** A policy describes intent. A tool built from a precise specification enforces it at the data layer. The system rejects writes that violate the rules. No policy document does that.
- **Agent identity is a structural requirement.** When AI agents have write access to governance data, identity verification and scope-bounded permissions are architectural preconditions.
- **Shared responsibility applies from day one.** The boundary between what the platform secures and what you own must be explicit before the first build starts.
- **The specification is the asset. The platform is the variable.** The codified rules, not the generated code, are the durable artefact.
- **The lifecycle model governs the tool. The specification governs the build.** An internally built AI tool requires the same operational discipline as any production system: named ownership, prompt observability, versioning, incident response, and defined decommissioning criteria. Speed to deploy does not reduce that obligation.

---

## The GRC Platform

The reference implementation demonstrates state machine governance applied to a multi-module GRC platform.

### Risk Lifecycle

Multi-phase lifecycle with hard-coded gate enforcement. Critical risks cannot be accepted. Mitigate requires linked controls via FK. Residual gate requires all five conditions confirmed. GRC Engineer validation required before treatments advance. Full detail: [State Transitions](./specification/state-transitions.md).

### Cross-Entity Propagation

Control failure freezes linked risk scores. Policy update flags mapped controls for re-assessment. Open issues above threshold prevent risk closure. Full cascade rules: [State Transitions §7](./specification/state-transitions.md#7-cross-lifecycle-cascade-rules).

### Threat Management and Engineering Integration

Engineering state (STRIDE threat models) governed through a 9-phase lifecycle bidirectionally linked to GRC state. Hard sign-offs enforced from AppSec and System_Owner. Active controls required for mitigation mappings (TINV-4). Unmitigated Medium+ threats automatically promoted. If a production control mitigating a threat fails, the cascade engine reverts the threat to Identified and demands rework.

### Agent Identity

System-signed tokens (OAuth 2.0 / SPIFFE/SPIRE). Scope-bounded permissions. Proposal/execution separation. Immutable audit. Out-of-scope attempts trigger suspension. Full detail: [Reference Architecture](./architecture/reference-architecture.md).

---

## The AI Tool Lifecycle Model

The lifecycle model extends the state machine approach to govern internally built AI tools themselves. It is not advisory. It defines enforced phases with gate conditions that must be satisfied before a tool advances.

Six phases: Ideation, Build, Pre-Production, Production, Maintenance, Deprecated.

The gate at Ideation requires a named owner before the first prompt is written. A tool without a confirmed owner cannot advance to Build. The gate at Pre-Production requires prompt telemetry confirmed in the SIEM before any user is onboarded. A tool without operational observability cannot enter Production. The gate at Maintenance requires quarterly kill-criteria assessment. A tool is deprecated deliberately, not abandoned.

Prompt logs are a detection surface, not a logging formality. Prompt injection, data exfiltration via crafted outputs, and anomalous usage patterns will not appear in application error logs. If prompt telemetry is not flowing into the SIEM before production deployment, the security gap is structural.

Full specification: [architecture/ai-tool-lifecycle.md](./architecture/ai-tool-lifecycle.md)

---

## Methodology

Four phases: **Codify** (governance rules to machine-readable) → **Specify** (artefact set per module) → **Build** (strict prompt cycle) → **Validate and Pin** (pass: advance, fail: fix spec, rebuild).

Core principle: fix the specification, not the code. Full detail: [/methodology](./methodology/).

---

## Regulatory Alignment

| Requirement | Regulation | Implementation |
|---|---|---|
| Continuous ICT risk monitoring with documented response | DORA Article 9 | Cross-entity FK propagation: issues and findings cascade to risk records |
| Incident management feeds back into risk register | DORA Article 11 | Planned: incident records will carry FK to risk records with a closure gate requiring risk record update. Specification in progress — see [APPENDIX.md#vulnerability-management](./APPENDIX.md#vulnerability-management) for the adjacent pattern. |
| ICT risk management framework maintained and reviewed | DORA Article 6 | Framework codified as machine-readable rule set. Changes trigger re-assessment cascade |
| ICT third-party register | DORA Article 28 | Third-party risk module: schema extension defined, state machine specified |
| AI system lifecycle documentation | EU AI Act Article 18 | Lifecycle model: Ideation through Deprecation artefacts satisfy technical documentation requirements |
| Continuous auth for all entities | NIST SP 800-207 | Agent identity layer: scope-bounded enforcement, immutable audit |
| Agentic scope containment | OWASP Agentic Security | Scope-bounded permissions prevent excessive agency |

---

## What's Next

**Vulnerability Management** — Five enforced state transitions: Discovery through Verified Closed. Specification in progress. [Detail](./APPENDIX.md#vulnerability-management).

**Resilience** — BIA/RPO/RTO as enforced state variables linked to risk register via FK. [Detail](./APPENDIX.md#resilience).

---

## Related

- [LinkedIn Article: Governance Is a State Machine. We've Been Treating It Like a Spreadsheet.](<!-- LINK TO ARTICLE -->)
- [LinkedIn Post Series](<!-- LINK TO POST 1 -->)

---

## Author

**Gavin Fitzpatrick** — Security architecture, GRC engineering, agentic AI development.

Two decades of experience scaling security programs across enterprise technology and financial services, including Meta, Coinbase, and enterprise data protection. MSc Security and Forensics. CISM. ISO 27001 Lead Implementer. Professional Diploma in AI. SANS DevSecOps.

Finds the problem. Builds the solution.
