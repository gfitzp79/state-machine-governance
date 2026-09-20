# The State Machine Model

**A Reference Architecture for Specification-Driven Security Tooling Built with Agentic AI**

---
> **Framework & IP Disclaimer:** This repository represents independent research. All data models, state transitions, and system invariants are strictly based on generic, public-domain industry frameworks (NIST SP 800-30, ISO 27005, FAIR). This codebase does not contain, reflect, or represent proprietary intellectual property, internal product roadmaps, or specific use-cases of any current or former employer. Read the full [disclaimer.md](./disclaimer.md).
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

## How This Repository Is Organised

Two things live here, and the relationship between them is the whole point.

| | What it is | Where | Licence | How you build it |
|---|---|---|---|---|
| **The framework** | A published specification: codified rules, state machines, invariants, data model, architecture, methodology | repository root | [CC BY 4.0](./LICENSE) | You do not. It is documents. |
| **The platform** | A reference implementation of that specification | [`platform/`](./platform) | [Apache 2.0](./platform/LICENSE) | `docker compose up -d`. See [platform/README.md](./platform/README.md). |

The framework drives the build, not the other way round. The specification is
the asset and the platform is the variable, so when the two disagree the
specification is right and the code has a defect. That ordering is the reason
the platform can be rewritten in a different language next year without any of
the governance work being lost.

### The framework documents

[`specification/codified-rules.md`](./specification/codified-rules.md) is the
source of truth. The rest derive from it and move with it.

| Document | What it holds | Source |
|---|---|---|
| [codified-rules.md](./specification/codified-rules.md) | Every governance rule, numbered, in machine-parseable form | The source of truth |
| [state-transitions.md](./specification/state-transitions.md) | Each lifecycle as states, gates, roles and preconditions | codified-rules §4-5, §9, §13, §19-20 |
| [invariants-catalogue.md](./specification/invariants-catalogue.md) | Every hard rule with its enforcement layer and mechanism | codified-rules §16-24 |
| [scoring-model.md](./specification/scoring-model.md) | The deterministic 5x5 scoring and control effectiveness model | codified-rules §4 |
| [architecture/data-model.md](./architecture/data-model.md) | The relational schema those rules require | codified-rules |

[`architecture/`](./architecture/) also covers deployment topologies, the shared
responsibility boundary, agent identity and the AI tool lifecycle.
[`methodology/`](./methodology/) covers how to build from a specification like
this one.

**There is no build step for the framework.** No toolchain, no generator,
nothing to install: the documents are the deliverable. Read them, cite them,
adapt them. What is automated is not a build but a consistency check, described
below, which fails CI if the documents and the code drift apart.

### One rule, end to end

The claim that the specification drives the build is only worth making if you
can follow a single rule the whole way. Take **RINV-5**, "Critical risks are
never accepted".

| Stage | Where | What is there |
|---|---|---|
| The rule | [codified-rules §5.5](./specification/codified-rules.md), `ACCEPTANCE_RULES` | `Critical: acceptance NOT PERMITTED, must Mitigate, Transfer, or Avoid` |
| The invariant | [invariants-catalogue.md](./specification/invariants-catalogue.md), row RINV-5 | Enforcement layer `Both`: a `CHECK` constraint and a service-layer rejection |
| Service enforcement | `platform/backend/app/modules/risk/invariants.py` | `_critical_never_accepted`, registered as `Invariant(id="RINV-5", ..., spec_ref="codified-rules section 5.5")` |
| Schema enforcement | `platform/backend/app/modules/risk/models.py` | `CheckConstraint(..., name="ck_risks_critical_never_accepted")` on the `risks` table |
| The test | `platform/backend/smoke_test.py` | Section `RINV-5: a Critical risk cannot be accepted`: asserts HTTP 409 and that the refusal names RINV-5 |
| The running system | `GET /api/engine/invariants` | Serves the RINV-5 row live. `RISK-003` in the demo data is Critical, so you can try it yourself |

The middle of that chain is not held together by review discipline. Two checks
run in CI on every push:

- `python tools/check_invariant_drift.py` fails the build if an invariant
  registered in code has no catalogue row, or declares an enforcement layer the
  catalogue disagrees with.
- `python tools/check_spec_references.py` fails it if an invariant cites a
  section of codified-rules that nobody wrote.

A rule enforced in code but absent from the documents is exactly the drift this
project exists to argue against, so it breaks the build rather than
accumulating quietly.

---

## Run It

The reference implementation is in [`/platform`](./platform). It is a working,
open-source GRC platform: modular, object-oriented, dockerised, and licensed
Apache-2.0.

```bash
git clone https://github.com/gfitzp79/state-machine-governance.git
cd state-machine-governance/platform
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8080> and sign in as `analyst@example.com` / `changeme123`.
Docker is the only prerequisite.

**9 state machines · 65 gated transitions · 65 invariants · 28 cascade events**,
served live from the running engine at `/api/engine/*` rather than transcribed
into a document that can drift.

Your operating model lives in
[`platform/config/governance.yml`](./platform/config/governance.yml): appetite
bands, control families, roles, acceptance windows, escalation SLAs, and
everything this specification marks `[CUSTOMISE]`.
Aligning the platform to your framework is a file edit and a restart, not a fork.
See the [configuration guide](./platform/docs/CONFIGURATION.md).

---

## The GRC Platform

The reference implementation demonstrates state machine governance applied to a multi-module GRC platform. Each section below names the specification section it implements, so the rule and the behaviour can be read side by side.

### Risk Lifecycle

Multi-phase lifecycle with hard-coded gate enforcement. Critical risks cannot be accepted. Mitigate requires linked controls via FK. Residual gate requires all five conditions confirmed. GRC Engineer validation required before treatments advance. Full detail: [State Transitions](./specification/state-transitions.md).

### Cross-Entity Propagation

Control failure freezes linked risk scores. Policy update flags mapped controls for re-assessment. Open issues above threshold prevent risk closure. Full cascade rules: [State Transitions §10](./specification/state-transitions.md#10-cross-lifecycle-cascade-rules).

### Threat Management and Engineering Integration

Engineering state (STRIDE threat models) governed through an 8-state lifecycle bidirectionally linked to GRC state. Hard sign-offs enforced from AppSec and System_Owner. Active controls required for mitigation mappings (TINV-4). Unmitigated Medium+ threats automatically promoted. If a production control mitigating a threat fails, the cascade engine reverts the threat to Identified and demands rework. Full detail: [State Transitions §7](./specification/state-transitions.md#7-threat-model-lifecycle-8-states).

### Compliance and Assurance

Every requirement of an adopted framework carries exactly one position, which makes the register a Statement of Applicability rather than a list of intentions. Coverage is derived from the control layer rather than asserted: a requirement is Covered only while a satisfying objective is Operating with a live deployment inside the framework's scope (AINV-2), and partial coverage is a gap, never coverage (AINV-3). When the control beneath a position fails, the cascade returns the requirement to Gap without anyone revisiting the register (AINV-5). Full detail: [State Transitions §9](./specification/state-transitions.md#9-requirement-assessment-lifecycle-6-states).

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
| Incident management feeds back into risk register | DORA Article 11 | Planned: incident records will carry FK to risk records with a closure gate requiring risk record update. Specification in progress: see [appendix.md](./appendix.md#vulnerability-management) for the adjacent pattern. |
| ICT risk management framework maintained and reviewed | DORA Article 6 | Framework codified as machine-readable rule set. Changes trigger re-assessment cascade |
| ICT third-party register | DORA Article 28 | Third-party risk module: schema extension defined, state machine specified |
| AI system lifecycle documentation | EU AI Act Article 18 | Lifecycle model: Ideation through Deprecation artefacts satisfy technical documentation requirements |
| Continuous auth for all entities | NIST SP 800-207 | Agent identity layer: scope-bounded enforcement, immutable audit |
| Agentic scope containment | OWASP Agentic Security | Scope-bounded permissions prevent excessive agency |

---

## What's Next

**Vulnerability Management**: five enforced state transitions, Discovery through Verified Closed. Specification in progress. [Detail](./appendix.md#vulnerability-management).

**Resilience**: BIA/RPO/RTO as enforced state variables linked to risk register via FK. [Detail](./appendix.md#resilience).

---

## Contributing

The repository moves at two speeds. The framework at the root is a published
specification people cite and build against, so it changes rarely and on
purpose. The platform is software and should move quickly.

Both halves are held together by checks rather than by review discipline: an
invariant added to the code without a catalogue entry fails the build, as does
one citing a specification section nobody wrote. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for how a framework improvement lands, and
[SECURITY.md](./SECURITY.md) before reporting a vulnerability.

---

## Licensing

This repository carries two licences, deliberately.

| | Covers | Licence |
|---|---|---|
| Repository root | The framework: specification, architecture, methodology | [CC BY 4.0](./LICENSE) |
| [`/platform`](./platform) | The reference implementation (software) | [Apache 2.0](./platform/LICENSE) |

Creative Commons advises against applying its licences to software, so the
implementation carries a licence built for code: permissive, with an explicit
patent grant and contributor terms.

The platform is versioned separately from the framework documents and follows
semantic versioning. It is currently **0.2.0**. Upgrades are migrated with
Alembic and an 0.1.0 database is adopted automatically on first boot. It stays
pre-1.0 because it has not yet been run in anger by anybody but its author. See
[CHANGELOG.md](./CHANGELOG.md) and the known limitations in
[platform/README.md](./platform/README.md).

---

## Related

- LinkedIn article: *Governance Is a State Machine. We've Been Treating It Like a Spreadsheet.* (link to follow)
- LinkedIn post series (links to follow)

---

## Author

**Gavin Fitzpatrick**: Security architecture, GRC engineering, agentic AI development.

Two decades of experience scaling security programs across enterprise technology and financial services, including Meta, Coinbase, and enterprise data protection. MSc Security and Forensics. CISM. ISO 27001 Lead Implementer. Professional Diploma in AI. SANS DevSecOps.

Finds the problem. Builds the solution.
