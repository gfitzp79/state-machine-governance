# Deployment Path 1: Agentic SaaS Platforms

**Version:** 2.0 | **License:** CC BY 4.0
**Source:** Derived from [Reference Architecture](./reference-architecture.md) §6 and [Shared Responsibility Model](./shared-responsibility.md)
**Purpose:** Architecture guide for deploying the governance platform onto an agentic SaaS build platform such as Lovable or Replit. Covers the two operating models, component architecture, platform-specific discipline, cost model, pre-production checklist, and decision criteria.

---

## Overview

An agentic SaaS platform provides the build environment, database engine, hosting, and deployment pipeline. You provide the specification, prompts, and governance validation. The agent generates the application code, schema, and API endpoints. You validate them against the specification before any user is onboarded.

**What you get:** Speed to prototype. No infrastructure to provision. Managed hosting, authentication, and database engine. A deployment that can go from a codified specification to a working stakeholder demo in hours to days.

**What you own:** The specification. The codified rules, invariants, RBAC definitions, state transitions, and scoring model. The validation of every piece of generated code against those rules. The operational governance of the tool from ideation through decommissioning.

**What the platform owns:** Infrastructure. Database engine uptime. TLS termination. Authentication service. Deployment pipeline. The platform's security certifications cover this layer -- not your application.

**Critical constraint:** The platform's SOC 2 or ISO 27001 certification does not extend to the code the agent generates. If the agent builds an insecure RLS policy, the platform runs an insecure RLS policy. Application-layer correctness is your responsibility in both deployment paths. See [Shared Responsibility Model](./shared-responsibility.md) §3 for the full responsibility matrix.

---

## Two Operating Models

Path 1 has two distinct operating models. The choice determines your vendor lock-in profile, your AppSec options, and your recovery path if the platform is unavailable or discontinued.

### Model A: GitHub-Connected (Recommended)

The platform connects to a GitHub repository. All agent-generated code is committed to the repository on every build. You retain a full, portable copy of the codebase at all times.

**How it works:**

1. Create a GitHub repository before the first prompt
2. Connect the repository to the platform (Lovable: Project Settings > GitHub; Replit: connect via the Git pane)
3. The platform syncs bidirectionally with the default branch
4. Every successful agent build produces a commit you can inspect, revert, and scan

**What this gives you:**

- Full commit history and the ability to revert to any prior state
- AppSec scanning in your own CI/CD pipeline on every agent commit
- Reduced vendor lock-in: the codebase is portable and the specification is always markdown
- A recovery path if the platform is unavailable: the codebase can be deployed elsewhere

**Critical discipline:** GitHub connection mitigates one class of context drift -- the agent building against stale code. It does not mitigate session-level invariant decay, where the agent begins contradicting prior architectural decisions. Re-grounding discipline applies in both operating models. See [Prompt Cycle](../methodology/prompt-cycle.md) §5.

### Model B: Platform-Native (Higher Lock-in)

Everything -- code, database, auth, and storage -- lives inside the platform. No external repository. Faster to start. Higher risk.

**When this is acceptable:**

- Personal or R&D builds with no production data
- Stakeholder demos where the goal is feedback, not operation
- Situations where the data classification permits full platform-hosted storage and you have reviewed the platform's DPA

**Critical requirements before committing any operational data:**

- Confirm the platform offers full data export (schema DDL, data rows, and codebase) before building
- Export the data model and architecture artefacts after every pinned module
- Document an explicit exit plan before onboarding the first user

**Lock-in risk:** Without a GitHub connection, your codebase is platform-native. If the platform changes pricing, discontinues the product, or suffers an extended outage, your recovery options are limited to whatever export capability the platform provides at that moment. The specification is always portable -- markdown files you own. The generated code may not be.

---

## Component Architecture

The platform provides the infrastructure stack. The components below are what a typical Lovable or Replit deployment provides, and what you are responsible for within them.

### Platform-Provided Components

| Component | What the Platform Provides | Your Responsibility |
|---|---|---|
| **Frontend runtime** | Hosting, CDN, HTTPS | Generated code correctness, RBAC gate implementation in UI |
| **Backend / API** | Serverless functions or managed container | Generated endpoint logic, role checks, invariant enforcement |
| **Database engine** | Managed PostgreSQL (Supabase on Lovable; Neon or equivalent on Replit) | Schema design, RLS policies, constraint correctness, migration management |
| **Authentication** | Built-in auth service (email, OAuth, magic link) | RBAC role assignment, session configuration, SSO if required |
| **File storage** | Platform-native object storage | Attachment policies, access control on stored objects |
| **Deployment pipeline** | Automated on commit or prompt | No action required -- agent deploys on build |
| **TLS / HTTPS** | Platform-managed certificate | Confirm enforced; no HTTP fallback permitted |

### Architecture Diagram (Logical -- Model A: GitHub-Connected)

```
┌──────────────────────────────────────────────────────────┐
│                   Agentic SaaS Platform                  │
│                                                          │
│  ┌──────────────┐        ┌───────────────────────────┐   │
│  │   Frontend   │        │    Backend / API Layer    │   │
│  │  (Hosted)    │◄──────►│  Phase gate enforcement   │   │
│  └──────────────┘        │  RBAC middleware          │   │
│                          │  Invariant validation     │   │
│                          └─────────────┬─────────────┘   │
│                                        │                  │
│                    ┌───────────────────┤                  │
│                    ▼                   ▼                  │
│           ┌──────────────┐   ┌──────────────────┐        │
│           │  PostgreSQL  │   │  Auth Service    │        │
│           │  (Managed)   │   │  (Platform)      │        │
│           │  RLS active  │   └──────────────────┘        │
│           └──────────────┘                                │
│                    │                                      │
│                    ▼                                      │
│           ┌──────────────┐                               │
│           │  Object      │                               │
│           │  Storage     │                               │
│           └──────────────┘                               │
└────────────────────┬─────────────────────────────────────┘
                     │ Two-way sync (Model A only)
                     ▼
          ┌──────────────────────┐
          │   GitHub Repository  │◄── CI/CD pipeline
          │   [REPO_NAME]        │    AppSec scanning
          └──────────────────────┘    Commit history
```

---

## Platform-Specific Guidance

### Lovable

Lovable is a React-focused agentic builder backed by Supabase for database and auth. The agent generates React components, Supabase schema migrations, and edge functions.

**Before the first prompt:**

- Create the GitHub repository and connect it in Project Settings before any build begins
- The platform only syncs the default branch -- confirm the branch name before connecting
- Validate your full specification in an optimised agent (Claude, GPT-4, or equivalent) before pushing any prompt to Lovable -- Lovable credits are consumed on every push regardless of output quality
- Design the complete schema before starting any application logic; schema changes after the first module is built are expensive on credit-based platforms

**During the build:**

- Batch related changes into single prompts where possible -- each push has a fixed credit overhead
- After every successful module, confirm the GitHub commit exists before proceeding
- When output quality degrades (agent re-implements existing components, contradicts prior schema, produces incomplete responses): stop. Revert to the last confirmed commit. Identify the specification gap. Update the specification. Rebuild. Do not send follow-up correction prompts to a degraded session.
- AppSec scanning should run in your CI/CD pipeline on every agent commit; do not wait until pre-production

**Supabase-specific:**

- RLS policies are generated by the agent but must be validated manually against your RBAC specification
- Confirm that every table with access-controlled data has RLS enabled -- generated scaffolding does not guarantee this
- Review the Supabase DPA for your region before committing any operational or personal data

### Replit

Replit supports a broader range of tech stacks and is used in both GitHub-connected and platform-native configurations. The Replit Agent can build across frontend, backend, and database layers within a single workspace.

**Before the first prompt:**

- Connect your GitHub repository via the Git pane before the first agent session
- Define your full tech stack before starting: Replit supports multiple stacks and the agent will make stack decisions if you do not specify them explicitly
- Replit workspaces can be shared; confirm workspace access controls before any sensitive data is introduced

**During the build:**

- Replit Agent sessions can degrade on large, multi-module builds; follow the same pin/revert discipline as Lovable
- For platform-native builds: use Replit's built-in snapshot capability as a pin point and export the data model and codebase to local storage after each pinned module
- Replit's database offering may vary by plan tier; confirm your database engine and its constraints before building schema

**For both platforms:**

- Confirm export capability (full codebase and data) before committing any production records
- When context drifts on large codebases, re-grounding requires a new session with the specification reloaded -- not more prompts in the degraded session
- See [Context Management](../methodology/context-management.md) for degradation detection signals and the full re-grounding sequence

---

## Cost Model

Agentic SaaS platforms charge per prompt, per database operation, and per code generation cycle. This is a consumption model, not a fixed infrastructure cost. Costs scale with the number of modules, the number of failed prompts that require revert and rebuild, and the complexity of the schema.

### Indicative Cost Factors

| Factor | Impact | Mitigation |
|---|---|---|
| Prompt count | Each push to the platform consumes credits regardless of success | Validate in optimised agent before pushing. Batch related changes. |
| Failed prompts | A failed prompt costs the same as a successful one | Specification quality before build. Pin/revert discipline. Do not iterate on broken output. |
| Schema changes post-build | Schema changes after logic is built require cascading rebuilds across dependent modules | Design the full schema before any application logic prompt. |
| Session context degradation | Degraded sessions produce low-quality output that may require full module rebuilds | Detect degradation early. Revert and re-ground before the damage compounds. |
| Hosting and database | Ongoing platform subscription or usage fee for hosted runtime and managed database | Review platform pricing tiers before committing to production use. |

### Build vs. Infrastructure Cost Comparison

| Cost Type | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| Build cost | Per-prompt credit consumption (variable) | Developer time + API credits (variable) |
| Infrastructure | Platform subscription or usage fee | ~$52-64/month estimated (see [self-hosted guide](./architecture-deployment-self-hosted.md)) |
| Scaling | Typically included in platform tier | Scales with compute and storage provisioned |
| Exit cost | Data export + redeploy effort | None -- you own the infrastructure |

The build cost for a multi-module platform on an agentic SaaS platform is real and non-trivial. Budget for iteration. Failed prompts that require revert and rebuild cost the same as successful ones. The optimisation practices in [Prompt Cycle](../methodology/prompt-cycle.md) reduce waste but do not eliminate it.

---

## Pre-Production Checklist

This checklist must be completed before any operational user is onboarded. It applies regardless of operating model. A stakeholder demo does not constitute pre-production validation.

### Application Layer

- [ ] Every RLS policy validated against the RBAC specification -- not assumed from generated scaffolding
- [ ] Every API endpoint role check validated server-side -- frontend gates are UX, not security
- [ ] Every phase gate transition tested: confirm conditions are enforced, not advisory
- [ ] Every hard invariant (NEVER, ALWAYS, MUST, BLOCKED) tested with adversarial inputs
- [ ] Input validation confirmed on all user-facing fields
- [ ] Agent permission scope defined and confirmed: which tables, which operations, which are prohibited
- [ ] AppSec review completed on generated codebase; findings resolved to agreed residual

### Operational Layer

- [ ] Named owner recorded in the AI Tool Lifecycle register before first user is onboarded
- [ ] Prompt observability active: input/output logging with anomaly thresholds defined
- [ ] Prompt telemetry confirmed flowing into SIEM or monitoring pipeline
- [ ] Runbook complete: operating procedures, restart paths, escalation contacts
- [ ] Incident response plan covers AI-specific failure modes including prompt injection
- [ ] Support model documented: escalation path from end user to named owner
- [ ] Maintenance capacity allocated: named percentage of team time reserved post-launch

### Data and Compliance

- [ ] Platform DPA reviewed and accepted for your data classification
- [ ] Data residency confirmed: platform region matches your data localisation requirements
- [ ] Export path confirmed and tested: full codebase and data export verified before operational data is committed
- [ ] Versioning strategy applied: build tagged at v0.x before pre-production validation begins

**Gate condition:** No user is onboarded until all items above are confirmed. Prompt observability and SIEM integration are not optional -- their absence is an unacceptable operational risk, not a deferred enhancement.

See [AI Tool Lifecycle](./ai-tool-lifecycle.md) §Phase 3 for the full pre-production artefact set.

---

## Vendor Lock-in Profile

| Component | Model A: GitHub-Connected | Model B: Platform-Native |
|---|---|---|
| Specification | Portable (markdown, your ownership) | Portable (markdown, your ownership) |
| Codebase | Portable (GitHub repository) | Platform-native (export required) |
| Database schema | Portable (PostgreSQL DDL) | Portable (PostgreSQL DDL, export required) |
| Database data | Platform-hosted (export required) | Platform-hosted (export required) |
| Authentication | Platform-native (migration required for path change) | Platform-native (migration required) |
| File storage | Platform-native | Platform-native |
| **Overall lock-in risk** | **MEDIUM** | **HIGH** |

**The specification is always portable.** The codified rules, invariants, state transitions, and scoring model are markdown files. If you need to migrate from Path 1 to Path 2, the specification is the rebuild blueprint. The generated code is disposable. The specification is the asset.

---

## When to Choose This Path

Choose Path 1 (Agentic SaaS) when:

- Speed to prototype or stakeholder demo is the primary objective
- No infrastructure engineering capacity is available internally
- Data classification permits platform-hosted storage (review DPA before committing data)
- Vendor lock-in risk is acceptable, or mitigated by GitHub sync (Model A)
- The use case is internal tooling, R&D, or a governed pilot -- not a system of record

Do not choose Path 1 when:

- Data sovereignty is a hard regulatory or contractual requirement
- The platform's DPA is incompatible with your data classification
- Production deployment with full CI/CD, AppSec pipeline, and infrastructure governance is required from day one
- Long-term economics favour fixed infrastructure cost over per-prompt consumption at your expected usage volume

For a side-by-side decision framework across both paths, see [Shared Responsibility Model §7](./shared-responsibility.md#7-decision-framework).

---

*This deployment guide is released under CC BY 4.0. Adapt freely with attribution.*
