# Prompt Cycle: Architectural Guidance for Agentic Builds

**Version:** 3.0 | **License:** CC BY 4.0
**Purpose:** Architectural guidance for structuring the prompt cycle across self-hosted agents and agentic SaaS platforms. Covers the optimised agent pattern, transforming codified rules into buildable architecture, prompt design, sequencing, and pin/revert discipline. Platform-agnostic: applies to Claude Code, Replit Agent, Lovable, or any agentic build tool.

> **Principle:** Each prompt is an atomic unit of work. The agent builds against it. You validate against the specification.

> **⚠ Cost awareness:** Agentic SaaS platforms charge per prompt, per database operation, and per code generation cycle. Self-hosted agents consume compute time and API credits. Before starting any build, understand your platform's pricing model, estimate total credit consumption for a multi-module build, and budget for iteration — failed prompts that require revert and rebuild cost the same as successful ones. The optimisation practices below reduce waste but do not eliminate cost. Factor this into your build-vs-buy decision.

> **Implementation companion:** This document covers architecture and discipline. For the actual prompt patterns — copy-paste templates for schema, CRUD pages, phase-gated workflows, RBAC, and dashboard widgets — see [Platform Prompt Library](./platform-prompt-library.md).

---

## Before You Start: Fill In These Parameters

This document contains bracketed parameters throughout. Replace each with your own values before using any prompt or guidance with an AI tool. Populate them once here and carry them consistently into every prompt.

```
[DOMAIN]          Your security or governance domain
                  e.g. GRC, Vulnerability Management, TPRM, Identity Governance, SIEM Triage

[PLATFORM]        Your chosen agentic build platform
                  e.g. Lovable, Replit Agent, Claude Code, Cursor + GitHub Copilot

[DB_PLATFORM]     Your database platform
                  e.g. Supabase (PostgreSQL), PlanetScale, Firebase, Neon

[TECH_STACK]      Your chosen frontend/backend stack
                  e.g. React + FastAPI, Next.js + Supabase Edge Functions, Vue + Node

[CLOUD]           Your cloud provider (if self-hosted)
                  e.g. AWS, GCP, Azure, Fly.io

[ORG_NAME]        Your organisation or project name (used in RBAC and audit context)
                  e.g. AcmeCorp Security, Personal Project

[PRIMARY_ENTITY]  The central governed object in your domain
                  e.g. Risk, Vulnerability, Incident, Policy, Vendor

[MODULE_1..N]     Your planned build modules in dependency order
                  e.g. Module 1: Platform and Identity, Module 2: Asset Register, Module 3: [PRIMARY_ENTITY] Lifecycle

[NUM_TABLES]      Approximate table count in your target schema
                  e.g. 12, 20, 35

[NUM_ROLES]       Number of RBAC roles in your platform
                  e.g. 5, 9

[LIFECYCLE_PHASES] Number of phases in your primary entity's lifecycle
                  e.g. 4 phases (Intake > Triage > Treatment > Monitoring),
                       7 phases (Intake > Preconditions > Scoring > Treatment > Readout > Evidence > Monitoring)

[INVARIANT_COUNT] Number of hard rules you have defined in your specification
                  e.g. 10, 30

[REPO_NAME]       Your GitHub repository name
                  e.g. my-org/vulnerability-platform

[DEPLOY_MODEL]    Your deployment target
                  e.g. Agentic SaaS (Model A: GitHub-connected), Agentic SaaS (Model B: platform-native),
                       Self-hosted on [CLOUD]
```

---

## 1. From Codified Rules to Object-State Architecture

Do this before touching any AI tool. The agent needs a technical blueprint, not a governance document.

**Step 1: Identify the objects.** Extract every persistent entity from your codified rules: `[PRIMARY_ENTITY]`, controls, policies, assets, users, roles. Each becomes a table with a lifecycle state.

**Step 2: Map the relationships.** For every entity pair: is there a relationship, what type (1:1, 1:N, M:M), does the join carry state (e.g. a snapshot field captured at assessment time), what foreign keys enforce it.

**Step 3: Define the state machines.** For every entity with a lifecycle: valid states, valid transitions, gate preconditions, cascade behaviours on state change. Your `[PRIMARY_ENTITY]` lifecycle has `[LIFECYCLE_PHASES]`.

**Step 4: Extract the invariants.** Every NEVER, ALWAYS, MUST, BLOCKED rule in your specification: which entity, what operation, which enforcement layer (schema constraint vs service layer gate). You have `[INVARIANT_COUNT]` to implement.

**Step 5: Design integrated workflows.** The cross-entity cascades: what triggers what across modules. Define these before any single-module build begins or the agent will implement each module in isolation.

**Output before any agent interaction:** Table-by-table schema with `[NUM_TABLES]` tables, state machine per entity with gates, cascade map, invariant-to-enforcement mapping. This is the technical blueprint.

---

## 2. Build Your Optimised Agent

Build a dedicated agent before writing your first build prompt. A generic prompt produces generic output. A tuned agent with deep context produces significantly better results — and on platforms charging per prompt, it pays back in reduced waste.

### Self-Hosted Agents (Claude Code, Cursor, Replit)

Create a persistent project context loaded at session start. This is your `claude.md`, `.replit` instructions, or equivalent briefing file depending on `[PLATFORM]`.

The briefing must contain:
- The current module being built (`[MODULE_1..N]` — one at a time)
- Data model for the current build phase (relevant tables only, not the full schema)
- Active invariants scoped to the current module
- Tech stack decision record: `[TECH_STACK]`, `[DB_PLATFORM]`, `[CLOUD]`
- Explicit prohibitions: what the agent must not change in already-pinned modules
- Current build state: what's pinned, what's in progress, what's next

Keep it concise and current. A stale 10,000-word briefing is worse than an accurate 500-word one.

**For Claude Code specifically:** Keep your `claude.md` maintained and current after every pinned module. This is the single highest-leverage lever for reducing unintended changes to stable code.

### Agentic SaaS Platforms (Lovable, Replit Agent)

Build a dedicated prompt agent in a separate AI conversation (Claude, ChatGPT, or equivalent) that understands both your specification and `[PLATFORM]`'s capabilities.

**Train it on the platform's documentation.** Every platform publishes prompting guides and capability constraints. Your agent needs this as foundational context: prompt structure, database capabilities, authentication model, known limitations. On `[PLATFORM]`, the relevant docs cover `[DB_PLATFORM]` integration, authentication patterns, and edge function constraints.

**Layer your specification on top.** The codified rules, target data model for the current module, active invariants, and acceptance criteria.

**Use this agent to draft and validate prompts before pushing to `[PLATFORM]`.** Every push costs credits. The optimised agent is your prompt pre-processor: draft, validate against spec, predict platform output, flag issues. Push only once validated.

---

## 3. Prompt Architecture

### What a prompt contains

**Schema context:** Tables, columns, constraints, and foreign keys relevant to this prompt. Not the full `[NUM_TABLES]`-table schema. Only what this prompt builds against plus FK references to adjacent tables.

**Business logic:** Rules, transitions, gate conditions, and invariants scoped to this module. Express as preconditions and postconditions, not prose.

**Definition of Done:** Explicit, testable acceptance criteria. Each criterion must be verifiable without subjective judgment. If you can't write a pass/fail test for it, rewrite the criterion.

### Prompt scope

| Scope | Example for `[DOMAIN]` | Typical Count |
|---|---|---|
| Table + CRUD | "Create `[PRIMARY_ENTITY]` table with constraints and basic endpoints" | 1 per table |
| State machine | "Implement `[LIFECYCLE_PHASES]` lifecycle with phase gates" | 1-2 per entity |
| Scoring engine | "Build scoring with control effectiveness resolution" | 1-2 total |
| Cascade logic | "Implement `[PRIMARY_ENTITY]` failure propagation to linked entities" | 1 per cascade chain |
| Integration | "Build treatment-to-ticketing webhook" | 1 per integration point |
| Dashboard | "Create executive `[PRIMARY_ENTITY]` KPI views" | 1-3 |

**Anti-pattern:** "Build the entire `[MODULE_1]` module." Too much scope. The agent makes unconstrained architectural decisions. Scope to one table, one state machine, or one cascade rule per prompt.

For proven prompt templates at each scope level, see [Platform Prompt Library](./platform-prompt-library.md).

### Sequencing

Follow the foreign key dependency chain. A build that ignores this order creates rework when the agent generates FK references to tables that don't exist yet.

The pattern below uses `[MODULE_1..N]` as placeholders. Replace with your actual module sequence based on your data model's dependency structure.

```
1. Platform and Identity    → users, roles, audit_log, notifications
2. [MODULE_1]               → foundation entities with no upstream FK dependencies
3. [MODULE_2]               → entities with FK dependencies on [MODULE_1]
4. [MODULE_N]               → entities with FK dependencies on prior modules
5. State machines           → lifecycle gates per entity (after all tables are pinned)
6. Scoring engine           → after state machines (depends on multiple entity states)
7. Cascade propagation      → after scoring (depends on cross-entity state)
8. Workflows                → approval chains, escalation, readout (after cascades)
9. Dashboards and reporting → after all data entities and workflows
10. Integrations            → last, after platform is stable
```

Each prompt builds on pinned output of the previous. If prompt 5 fails, do not touch prompts 1-4.

---

## 4. The Pin/Revert Discipline

### Pin

After every successful prompt (all acceptance criteria pass):

- **Self-hosted (`[PLATFORM]` = Claude Code / Cursor):** `git commit` with a descriptive message. Tag milestones. Repository: `[REPO_NAME]`.
- **Agentic SaaS (`[PLATFORM]` = Lovable / Replit Agent, GitHub-connected):** The platform auto-commits to `[REPO_NAME]`. Confirm the commit exists before proceeding.
- **Agentic SaaS (platform-native):** Use the platform's snapshot or restore point feature. Export the data model and codebase to a local copy immediately after each pin.

### Revert

When a prompt fails:

- **Do not** send follow-up "fix" prompts. This compounds context drift and costs additional credits with no guarantee of recovery.
- **Do** revert to the last pin. Identify the specification gap. Update the spec. Rebuild.

### Why this matters

Without pin discipline there is no recovery path. A failure in prompt 8 can corrupt prompt 6 output if you iterate without reverting. The agent's failed context contaminates subsequent work. The pin is what makes the correction protocol possible.

---

## 5. Platform-Specific Guidance

### Self-Hosted (Claude Code, Cursor, Replit with local agent)

- Maintain your briefing file (`claude.md` or equivalent); update it before every session, not after
- Version control from the first prompt — repository `[REPO_NAME]`, commit before any new prompt
- End every prompt with the DoD as a numbered checklist the agent can self-check against
- Keep `[TECH_STACK]` decision locked before the build starts; mid-build stack changes are expensive
- When context degrades (agent re-implements existing components, contradicts prior architecture, produces verbose generic responses): start a new session, reload the briefing, continue from the last pin

### Agentic SaaS (Lovable, Replit Agent — GitHub-Connected)

- Connect `[REPO_NAME]` to the platform before the first prompt — the platform only syncs the default branch
- Validate prompts in your optimised agent before pushing to `[PLATFORM]` (saves credits)
- Batch related changes into single prompts where possible — each push to the platform has a fixed overhead
- The GitHub connection mitigates one class of context drift (agent building against stale code) but not session-level invariant decay — re-grounding discipline still applies
- AppSec scanning should run in your CI/CD pipeline against `[REPO_NAME]` on every agent commit

### Agentic SaaS (Platform-Native, No GitHub)

- Design the full `[NUM_TABLES]`-table schema before starting any application logic — schema changes after logic is built are expensive on credit-based platforms
- Export the data model and architecture artefacts after every pinned module; re-import into your optimised agent to maintain external context
- Confirm export capability for data and codebase before committing any production records to `[DB_PLATFORM]`
- When output quality degrades: stop, export, validate against specification, re-ground in a new session. Do not send additional prompts to a degraded session.

See: [Context Management](./context-management.md) for degradation detection signals and the full re-grounding sequence.

---

## 6. The Correction Protocol

Two failure modes appear in every multi-module agentic build. Both are resolved by fixing the specification, not the code.

**Failure Mode 1: Circular Dependency**
Two components each depend on the other to resolve a value. The build either loops or defaults to an undefined value. Root cause: the specification did not define computation order. Fix: declare an explicit resolution order in the spec — which component resolves first and is treated as a fixed input to the other. Update the spec. Rebuild from the last pin.

**Failure Mode 2: Silent Gate Removal**
A state transition gate is rewritten by the agent to resolve an unrelated conflict (rendering, type error, schema change). The component works. The invariant is absent. This is the most dangerous failure mode because nothing breaks visibly. Root cause: the spec described the invariant as a lifecycle rule but did not declare it inviolable at the code layer. Fix: explicitly declare the invariant inviolable in the spec and state that no other requirement can justify its removal.

### The Protocol

```
1. Identify the specification gap
   What instruction was absent or ambiguous that permitted this failure?

2. Update the constraint document
   Add the missing rule. Be precise enough that no reasonable interpretation
   permits the failure mode to recur.

3. Clear agent context
   Start a new session. Residual failed context contaminates corrections.

4. Rebuild affected components only
   Return to the last pin. Rebuild only what failed.
   Do not touch pinned components that passed their acceptance criteria.
```

This is the core discipline of agentic engineering. The failure mode is almost never "the agent didn't understand the task." It is "the specification didn't constrain the problem precisely enough."

---

*Released under CC BY 4.0. Adapt freely with attribution.*
