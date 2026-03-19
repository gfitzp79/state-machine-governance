# Deployment Path 1: Agentic SaaS Platforms

**Version:** 3.0-template | **License:** CC BY 4.0
**Source:** Derived from [Reference Architecture](./reference-architecture.md) §6 and [Shared Responsibility Model](./shared-responsibility.md)
**Purpose:** Architecture guide for deploying the governance platform onto agentic SaaS platforms. Covers two distinct operating models, cost dynamics, security boundaries, observed failure patterns, and decision criteria.

---

## Overview

Agentic SaaS platforms accept a specification and prompt package, generate the application, and host it with out-of-the-box infrastructure: authentication, database, deployment pipeline, and a shareable URL. The builder provides the governance logic. The platform provides the runtime.

**What you get:** Speed to deployment. A shareable URL for stakeholder review. Authentication, database hosting, and TLS without infrastructure provisioning. Iteration via prompts rather than deployment pipelines.

**What you own:** The application logic, the data model, the agent's permission scope, the RBAC and RLS configuration, the invariant enforcement, and the AppSec validation of all generated code.

**What the platform owns:** Hosting infrastructure, database engine, TLS certificates, uptime SLA, deployment pipeline, and platform-level security controls.

---

## Two Operating Models

This path splits into two distinct operating models with different risk profiles, workflows, and technical requirements. Choose before you start the build — switching models mid-build is possible but disruptive.

---

### Model A: GitHub-Connected Build (Recommended)

**Who this suits:** Practitioners with GitHub familiarity, teams collaborating with engineers, or anyone prioritising codebase portability and reduced vendor lock-in.

In this model, the agentic SaaS platform is a code generation and hosting layer. Your codebase lives in GitHub as the single source of truth. Two-way sync means edits in the platform appear in GitHub and edits in GitHub sync back to the platform on the default branch.

**Key properties:**
- Codebase owned and version-controlled by you from day one
- Full commit history, branching, and pull request capability
- Local IDE editing with changes syncing back to the platform
- AppSec scanning runs in your own CI/CD pipeline against code you control
- Platform becomes a generation interface, not a code custody layer
- Vendor lock-in risk reduced significantly: specification and codebase are both portable

**Important constraints from the platform:**
- Connect GitHub at the start of the build or when first deploying — you cannot import an existing external codebase into the platform from GitHub; export only runs from the platform outward
- The platform only syncs the default branch (typically `main`); feature branches must be merged before changes appear in the platform
- The connection depends on the exact repository name, location, organisation, and account — do not rename, move, or delete the repository after connecting, as this breaks sync

**Build workflow:**

```
1. Create GitHub repository          → establish single source of truth before first prompt
2. Connect platform to GitHub        → Settings → Connectors → GitHub → Connect project
3. Codified specification            → prepared offline (no platform cost)
4. Local prompt agent                → optimised agent with spec + platform docs as context
5. Validate prompts locally          → test against specification before pushing (saves credits)
6. Platform build                    → each prompt consumes credits; code commits to GitHub
7. Validation                        → acceptance criteria checked per prompt; pin or revert
8. Deployment                        → platform auto-deploys from GitHub main; shareable URL generated
9. Iteration                         → further prompts via platform or direct commits to GitHub
```

**Context management advantage:**
Because the platform is always building against the live GitHub codebase, one category of context drift is mitigated: the agent is less likely to re-implement or contradict components it can read from the repository. Session-level context window degradation still applies — the re-grounding disciplines in [context-management.md](../methodology/context-management.md) remain relevant and should not be skipped. But the GitHub-connected model removes the risk of the agent working against a stale snapshot of the codebase.

---

### Model B: Platform-Native Build

**Who this suits:** Non-engineers, practitioners without GitHub familiarity, or rapid prototyping where portability is not the immediate priority.

In this model, the platform is the complete environment: prompt interface, codebase, database, auth, and deployment. Everything lives inside the platform. This is faster to start and has no external tooling dependencies, but carries higher vendor lock-in risk and requires deliberate data portability planning.

**Key properties:**
- No GitHub account or setup required
- Lower barrier to entry for non-engineers
- Single environment for all build and iteration work
- Higher vendor lock-in: codebase is platform-native until manually exported
- Data portability requires explicit planning; confirm export capability before committing production data
- Context management relies entirely on briefing files, prompt discipline, and regular data model exports

**Build workflow:**

```
1. Codified specification            → prepared offline (no platform cost)
2. Platform prompt agent             → build optimised agent within the platform using vendor docs
3. Platform build                    → each prompt consumes credits (prompt + DB operations + code generation)
4. Validation                        → acceptance criteria checked per prompt; pin or revert
5. Deployment                        → platform auto-deploys; shareable URL generated
6. Iteration                         → further prompts for refinement, each consuming credits
7. Export regularly                  → export codebase and data model periodically for portability
```

**Context management requirement:**
Without GitHub sync, context degradation is a higher operational risk. The full re-grounding methodology in [context-management.md](../methodology/context-management.md) applies without mitigation. Regularly export the data model and architecture artefacts and re-import them into your prompt agent to maintain external context across sessions.

---

## Cost Dynamics (Both Models)

The consumption model is not linear. Every prompt processed, every database table created, every row updated, and every code optimisation consumes credits. On a multi-module platform (risk, controls, policy, asset register, dashboards), credit consumption compounds.

| Phase | Cost Driver | Mitigation |
|---|---|---|
| Initial build | Prompt volume × complexity | Validate prompts locally before pushing. Batch related changes into single prompts. |
| Schema changes | Table creation, column addition, constraint modification | Design the full schema before starting the build. Avoid iterative schema discovery on-platform. |
| Data operations | Seed data, test records, bulk operations | Minimise test data operations during build. Import seed data in a single operation. |
| Iteration | Refinement prompts, bug fixes, UI adjustments | Pin stable versions. Revert and rebuild from spec rather than patching. |
| Steady state | Hosting, database, user sessions | Generally low. Platform pricing models vary: review per-seat vs. per-usage terms. |

**Model A cost note:** Prompts validated locally against your specification before pushing reduce wasted credit spend materially. The GitHub connection itself does not add platform cost.

---

## Infrastructure Provided (Both Models)

| Component | Platform Provides | Your Responsibility |
|---|---|---|
| Database | Managed PostgreSQL (or equivalent) | Schema design, RLS policies, data integrity, backup verification |
| Authentication | Built-in auth (email/password, social, or OIDC) | RBAC configuration, role assignment, session management validation |
| Hosting | Container or serverless deployment | Application logic correctness, API security, error handling |
| TLS | HTTPS by default | Custom domain configuration (if required) |
| Storage | File storage for attachments | Access control on stored files, encryption-at-rest configuration |

---

## Security Boundary

The platform's security certification does not extend to your application. Two failure patterns apply to both models.

### Failure Pattern 1: Agent Permission Overreach

Without explicit scope constraints defined in the specification, agents default to broad database privileges. Observed behaviours include:

- Bulk delete operations on production data executed by the agent during a "cleanup" prompt
- Record fabrication where the agent creates test data that persists in production tables
- Schema modifications where the agent adds, removes, or alters columns without explicit instruction

**Root cause:** The specification did not define what the agent is permitted to do. The platform executed the agent's actions correctly. The governance failure is in the specification, not the platform.

**Mitigation:** Define agent permission scope in the specification before the first build prompt. Explicitly declare which tables the agent may modify, which operations are permitted (CREATE, READ, UPDATE, DELETE per table), and which operations are prohibited.

**Model A note:** GitHub sync records every agent-generated commit. This creates a full audit trail and makes it straightforward to identify and revert unintended schema modifications.

### Failure Pattern 2: Misconfigured Application-Layer Controls

AI-generated scaffolding creates authentication flows, database structures, and API endpoints quickly. The following require explicit validation because their existence does not confirm their correctness:

- **Row Level Security (RLS):** Policies may exist but not enforce the correct data isolation boundaries. A user in Role A may be able to read records belonging to Role B if RLS policies are generated but not validated against the RBAC specification.
- **API key scoping:** Generated API endpoints may not enforce role-based access at the API layer, relying instead on UI-level hiding which can be bypassed.
- **Role definitions:** The platform may create role structures that do not match the 9-role RBAC model in the specification. Validation against the spec is required.

**Root cause:** The platform generated controls. The specification did not define the expected behaviour of those controls precisely enough for validation.

**Mitigation:** After initial build, validate every RLS policy, every API endpoint's role check, and every role definition against the codified specification. Treat this as a mandatory gate before sharing the URL with any stakeholder.

**Model A note:** In the GitHub-connected model, AppSec scanning can be integrated into the CI/CD pipeline, providing automated validation on every commit rather than manual post-build inspection.

---

## Vendor Lock-in

| Model | Overall Risk | Specification | Codebase | Database | Auth |
|---|---|---|---|---|---|
| **Model A: GitHub-Connected** | MEDIUM | Portable | Portable (GitHub) | Platform-native | Platform-native |
| **Model B: Platform-Native** | HIGH | Portable | Platform-native | Platform-native | Platform-native |

In both models, the specification is portable. The codebase portability difference is the primary distinction. For full data and infrastructure portability, Path 2 (self-hosted) remains the lowest lock-in option.

Full assessment: [Shared Responsibility Model](./shared-responsibility.md#6-vendor-lock-in-comparison).

---

## Decision Gate

**Model A: GitHub-Connected**

Before starting the build, confirm:

```
□ GitHub repository created and connected to platform before first prompt
□ Shared responsibility boundary documented and accepted by risk owner
□ Agent permission scope defined in specification
□ CI/CD pipeline configured for AppSec scanning on commits
□ RLS policies validated against RBAC specification post-build
□ Data processing terms reviewed (residency, encryption, model API usage)
□ Cost model projected for 12-month steady state
```

**Model B: Platform-Native**

Before deploying production data, confirm:

```
□ Shared responsibility boundary documented and accepted by risk owner
□ Agent permission scope defined in specification
□ RLS policies validated against RBAC specification post-build
□ Data processing terms reviewed (residency, encryption, model API usage)
□ Export capability confirmed for data and codebase portability
□ Cost model projected for 12-month steady state
□ Re-grounding methodology from context-management.md in place
```

For guidance on when this path is appropriate vs. self-hosted or vendor platforms: [Shared Responsibility Model §7](./shared-responsibility.md#7-decision-framework).

---

*This deployment guide is released under CC BY 4.0. Adapt freely with attribution.*
