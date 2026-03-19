# Prompt Cycle: Architectural Guidance for Agentic Builds

**Version:** 2.1 | **License:** CC BY 4.0
**Purpose:** Architectural guidance for structuring the prompt cycle across self-hosted and agentic SaaS deployment paths. Covers the optimised agent pattern, transforming codified rules into buildable architecture, prompt design, and pin/revert discipline.

> **Principle:** Each prompt is an atomic unit of work. The agent builds against it. You validate against the specification.

> **⚠ Cost awareness:** Agentic SaaS platforms charge per prompt, per database operation, and per code generation cycle. Self-hosted agents consume compute time and API credits. Before starting any build, understand your platform's pricing model, estimate total credit consumption for a multi-module build, and budget for iteration (failed prompts that require revert and rebuild cost the same as successful ones). The optimisation practices below help reduce waste, but they do not eliminate cost. Factor this into your build-vs-buy decision.

> **Implementation companion:** This document covers architecture and discipline. For the actual prompt patterns — copy-paste templates for schema, CRUD pages, phase-gated workflows, RBAC, and dashboard widgets — see [Platform Prompt Library](./platform-prompt-library.md).

---

## 1. Step Zero: Build Your Optimised Agent

Before writing your first build prompt, create a dedicated agent optimised for your governance platform. A generic prompt produces generic output. A tuned agent with deep context produces dramatically better results.

### Self-Hosted Agents

Create a persistent project context loaded at session start:
- Current module's codified rules specification
- Data model for the current build phase
- Active invariants (filtered to current module)
- Tech stack decision record
- Explicit prohibitions: what the agent must not change
- Current build state: what's done, what's next

Keep it concise and current. A stale 10,000-word briefing is worse than an accurate 500-word one.

### Agentic SaaS Platforms

Build a dedicated prompt agent in your AI tool of choice (Claude, ChatGPT, Gemini) that understands both your specification and the platform's capabilities.

**Train the agent on the platform's documentation.** Every platform publishes prompting guides and best practices. Your agent should have this as foundational context: prompt structure, database capabilities, authentication model, known limitations.

**Layer your governance specification on top.** The codified rules, target data model, invariants, and acceptance criteria for the current module.

**Use this agent to draft and validate prompts before pushing.** Every push costs credits. The optimised agent acts as your prompt pre-processor: draft, validate against spec, predict platform output, flag issues. Only push once validated.

---

## 2. From Codified Rules to Object-State Architecture

The codified rules are a governance document. Transform them into a technical blueprint before the agent builds.

**Step 1: Identify the objects.** Extract every persistent entity: Risks, Controls, Policies, Standards, Exceptions, Treatments, Assets, Issues, Users, Roles. Each becomes a table with a lifecycle.

**Step 2: Map the relationships.** For every entity pair: is there a relationship, what type (1:1, 1:N, M:M), does it carry state (e.g. CE snapshot in `risk_controls`), what FKs enforce it.

**Step 3: Define the state machines.** For every entity with a lifecycle: valid states, valid transitions, gate preconditions, cascade behaviours on state change.

**Step 4: Extract the invariants.** Every "NEVER," "ALWAYS," "MUST," "BLOCKED" rule: which entity, what operation, which enforcement layer.

**Step 5: Design integrated workflows.** The cross-entity cascades: control failure → risk frozen → escalation. CE improvement → residual eligible → gate required. Policy revision → control alignment → SLA tracking. Issue from test failure → CE re-assessment.

**Output:** Table-by-table schema, state machine per entity with gates, cascade map, invariant-to-enforcement mapping. This is what the agent builds against.

---

## 3. Prompt Architecture

### What a prompt contains

**Schema context:** Tables, columns, constraints, and FKs relevant to this prompt. Not the full 20-table schema. Only what this prompt builds against plus FK references to adjacent tables.

**Business logic:** Rules, transitions, gate conditions, and invariants. Express as preconditions and postconditions, not prose.

**Definition of Done:** Explicit, testable acceptance criteria. Each verifiable without subjective judgment.

### Prompt scope

| Scope | Example | Typical Count |
|---|---|---|
| Table + CRUD | "Create risks table with constraints and endpoints" | 1 per table |
| State machine | "Implement 7-phase risk lifecycle with gates" | 1-2 per entity |
| Scoring engine | "Build scoring with CE resolution" | 1-2 total |
| Cascade logic | "Implement control failure → risk propagation" | 1 per chain |
| Integration | "Build treatment-to-ticketing webhook" | 1 per point |
| Dashboard | "Create executive risk KPI views" | 1-3 |

**Anti-pattern:** "Build the entire risk management module." Too much scope for the agent to make unconstrained decisions.

For proven prompt templates at each scope level, see [Platform Prompt Library](./platform-prompt-library.md).

### Sequencing

Follow the FK dependency chain:

```
1. Platform (users, roles, audit_log)
2. Asset register (assets, systems)
3. Controls (objectives → activities → deployments)
4. Policies (policies → standards → exceptions)
5. Risks (risks → risk_controls → risk_treatments)
6. State machines (lifecycle gates per entity)
7. Scoring engine
8. Cascade propagation
9. Workflows (treatment, escalation, readout)
10. Dashboards and reporting
11. Integrations
```

Each prompt builds on pinned output of previous prompts. If prompt 5 fails, don't touch 1-4.

---

## 4. The Pin/Revert Discipline

### Pin

After every successful prompt (all acceptance criteria pass):
- **Self-hosted:** `git commit` with descriptive message. Tag milestones.
- **SaaS:** Platform snapshot if available. Otherwise export codebase and commit locally.

### Revert

When a prompt fails:
- **Do not** send follow-up "fix" prompts. This compounds context drift.
- **Do** revert to last pin, identify the spec gap, update the spec, rebuild.

### Why this matters

Without pin discipline there is no recovery path. A failure in prompt 8 can corrupt prompt 6 output if you iterate without reverting. The agent's failed context contaminates subsequent work. Pinning makes the correction protocol possible.

---

## 5. Platform Guidance

### Self-Hosted

- Maintain project-level briefing file; agent reads at session start
- Version control from the first prompt. Not optional.
- End every prompt with the DoD as a numbered checklist
- When context degrades (agent conflicts with earlier work, re-implements existing components): new session, reload briefing, continue from last pin

### Agentic SaaS

- Validate prompts in your optimised agent before pushing (saves credits)
- Batch related changes into single prompts where possible
- Define the full schema before building any application logic (schema changes after logic is built are expensive)
- Export data model regularly; re-import into optimised agent to maintain external context
- When output quality degrades: stop, export, validate, re-ground. Do not send more prompts.

See: [Context Management](./context-management.md) for degradation detection and re-grounding strategies.
See: [Platform Prompt Library](./platform-prompt-library.md) for copy-paste prompt templates derived from a production build.

---

*Released under CC BY 4.0. Adapt freely with attribution.*
