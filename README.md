# The State Machine Model

**A Reference Architecture for Specification-Driven Security Tooling Built with Agentic AI**

---
> **Framework & IP Disclaimer:** This repository represents independent research. All data models, state transitions, and system invariants are strictly based on generic, public-domain industry frameworks (NIST SP 800-30, ISO 27005, FAIR). This codebase does not contain, reflect, or represent proprietary intellectual property, internal product roadmaps, or specific use-cases of any current or former employer. Read the full [DISCLAIMER.md](./DISCLAIMER.md).
---

## What This Is

A reference architecture and methodology for building security tooling that enforces state machine logic natively, using specification-driven agentic AI development. The reference implementation is a GRC platform. The methodology applies to any security domain where the gap between policy intent and tool enforcement is wide.

Codified governance rules, data models, deployment architecture, and the complete methodology to build from them.

## Why It Exists

Enterprise security and GRC tooling is typically designed around a vendor's model of how governance should work. Teams configure their frameworks to fit the platform, not the other way around. The right architecture inverts this: tooling that conforms to your framework, your rules, your operating model. When teams can specify and build precisely, the quality bar for what a vendor platform must offer also rises.

Teams with precise specifications can now build exact implementations of their security and governance frameworks in weeks using agentic AI, rather than months of vendor configuration.

## Core Thesis

- **Governance is a state machine, not a spreadsheet.** Risks, controls, issues, and policies are interconnected entities whose state changes propagate across the system.
- **Precise specifications enforce what can happen, not just what should happen.** A policy describes intent. A tool built from a precise specification enforces it at the data layer. The system rejects writes that violate the rules. No policy document does that.
- **Agent identity is a structural requirement.** When AI agents have write access to governance data, identity verification and scope-bounded permissions are architectural preconditions.
- **Shared responsibility applies from day one.** The boundary between what the platform secures and what you own must be explicit before the first build starts.
- **The specification is the asset. The platform is the variable.** The codified rules, not the generated code, are the durable artefact.

## Contents

```
├── README.md
├── DISCLAIMER.md
├── APPENDIX.md                     # DORA mapping, VM and Resilience specs, references
│
├── /specification
│   ├── codified-rules.md           # Machine-readable governance rule set
│   ├── invariants-catalogue.md     # Enforcement rules with layer and mechanism
│   ├── state-transitions.md        # Phase gate definitions and preconditions
│   └── scoring-model.md            # Scoring engine implementation spec
│
├── /architecture
│   ├── reference-architecture.md   # Platform overview: schema, lifecycle, cascade, RBAC
│   ├── data-model.md               # 20-table schema with DDL
│   ├── deployment-saas.md          # Path 1: Agentic SaaS deployment
│   ├── deployment-self-hosted.md   # Path 2: Self-hosted cloud infrastructure
│   └── shared-responsibility.md    # SRM analysis across deployment paths
│
├── /methodology
│   ├── specification-driven-dev.md # The methodology
│   ├── prompt-cycle.md             # Prompt design, agent optimisation, sequencing
│   └── context-management.md       # Context degradation and re-grounding
│
└── /diagrams
    ├── state-machine.png
    ├── methodology.png
    └── integration.png
```

**If you're here from the article:** The `/specification` folder contains the codified rules and enforcement catalogue. The `/methodology` folder contains the prompt cycle and context management guides. The `/architecture` folder contains the data model and both deployment paths. Start with `specification/codified-rules.md` to understand the governance logic before looking at any generated code.

## Architecture at a Glance

### Risk Lifecycle: 7 Phases, Hard-Coded Gates

```
Intake → Preconditions → Scoring → Treatment → Readout → Evidence+Residual → Monitoring
  │           │              │          │           │              │               │
REJECT     REJECT         REJECT     REJECT      REJECT        REJECT          REJECT
```

Key enforcement rules: Accept requires time-bound expiry (NOT NULL). Critical risks cannot be accepted. Mitigate requires linked controls via FK. Residual gate requires all 5 conditions confirmed. GRC Engineer validation required before treatments advance. Full detail: [State Transitions](./specification/state-transitions.md).

### Cross-Entity Propagation

Control failure → linked risk scores frozen. Policy update → mapped controls flagged for re-assessment. Open issues above threshold → risk cannot close. Full cascade rules: [State Transitions §7](./specification/state-transitions.md#7-cross-lifecycle-cascade-rules).

### Agent Identity

System-signed tokens (OAuth 2.0 / SPIFFE/SPIRE). Scope-bounded permissions. Proposal/execution separation. Immutable audit. Out-of-scope attempts trigger suspension. Full detail: [Reference Architecture](./architecture/reference-architecture.md).

## Methodology

Four phases: **Codify** (governance rules → machine-readable) → **Specify** (artefact set per module) → **Build** (strict prompt cycle) → **Validate and Pin** (pass: advance, fail: fix spec, rebuild).

Core principle: fix the specification, not the code. Full detail: [/methodology](./methodology/).

## Regulatory Alignment

- **DORA** — Articles 9, 11: cross-entity FK propagation implements continuous monitoring and incident-to-risk feedback
- **NIST SP 800-207** — Agent identity layer: continuous auth for all entities
- **CBI accountability framework** — Cascading state machine satisfies mandatory integrated ICT risk management
- **OWASP Agentic Security** — Scope-bounded enforcement prevents excessive agency

## What's Next

**Vulnerability Management** — 5 enforced state transitions: Discovery → Verified Closed. [Detail](./APPENDIX.md#vulnerability-management).

**Resilience** — BIA/RPO/RTO as enforced state variables linked to risk register via FK. [Detail](./APPENDIX.md#resilience).

## Related

- [LinkedIn Article: Security Teams Can Build Their Own Tools Now. Here's How I Did It.](<!-- LINK TO ARTICLE -->)
- [LinkedIn Post Series](<!-- LINK TO POST 1 -->)

## Author

**Gavin Fitzpatrick** — Security architecture, GRC engineering, agentic AI development.

Two decades of experience scaling security programs across enterprise technology and financial services, including Meta, Coinbase, and enterprise data protection. MSc Security and Forensics. CISM. ISO 27001 Lead Implementer. Professional Diploma in AI. SANS DevSecOps.

Finds the problem. Builds the solution.

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [DISCLAIMER.md](./DISCLAIMER.md).
