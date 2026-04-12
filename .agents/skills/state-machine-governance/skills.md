---
name: state-machine-governance
description: "Maintains and extends a markdown-based GRC reference architecture repository. Use this skill when adding a new governance domain (e.g., threat management, vulnerability management, resilience), adding or modifying invariants, extending state machine lifecycles, updating data model tables, or reviewing cross-document consistency across specification, architecture, and methodology documents. This repo contains no source code — all outputs are markdown specification documents. Do NOT use for source code generation, deployment configuration, or any task unrelated to GRC specification authoring."
license: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
---

# State Machine Governance — Specification Maintenance Skill

## What This Skill Covers

Authoring and maintaining the markdown documents that make up the state-machine-governance reference architecture. Every task involves one or more of the following document types:

- Governance rules and invariants (`specification/`)
- Data models and architecture guides (`architecture/`)
- Methodology and prompt guidance (`methodology/`)
- Entry points and regulatory mapping (`README.md`, `appendix.md`)

No source code is produced. The specification documents are the deliverable.

---

## Before Starting Any Task

Read `@.agents/agents.md` in full. It contains the document map, cross-document dependency rules, editorial standards, and the list of things the agent must not do. These apply to every task regardless of scope.

Then read the specific documents relevant to the task. Do not rely on training knowledge about what these documents contain — read them.

---

## Task Decision Tree

Use this to determine which documents are in scope before starting work.

```
What are you doing?
│
├── Adding a new governance domain (e.g., Incident Management, Resilience)
│   Read:  @specification/codified-rules.md (for existing domain structure to follow)
│           @specification/state-transitions.md (for existing lifecycle format)
│           @specification/invariants-catalogue.md (for existing invariant table format)
│           @architecture/data-model.md (for existing domain section format)
│   Touch: codified-rules.md → state-transitions.md → invariants-catalogue.md
│           → data-model.md → appendix.md → README.md
│
├── Adding or modifying an invariant
│   Read:  @specification/codified-rules.md §[relevant section]
│           @specification/invariants-catalogue.md (check for ID conflicts)
│           @specification/state-transitions.md (if invariant gates a transition)
│   Touch: codified-rules.md → invariants-catalogue.md
│           → state-transitions.md (if transition-gating)
│
├── Adding or modifying a state or transition
│   Read:  @specification/codified-rules.md §[lifecycle section]
│           @specification/state-transitions.md §[lifecycle section]
│           @architecture/data-model.md (check lifecycle_state enum column)
│   Touch: codified-rules.md → state-transitions.md (diagram + table)
│           → data-model.md (if enum changes)
│
├── Adding or modifying a table or column
│   Read:  @architecture/data-model.md §[domain section]
│           @architecture/data-model.md §9 (FK map)
│           @architecture/data-model.md §10 (constraint summary)
│   Touch: data-model.md (table + FK map + constraint summary)
│           → reference-architecture.md (if top-level entity)
│
├── Adding a cascade rule
│   Read:  @specification/codified-rules.md (cascade trigger format)
│           @specification/state-transitions.md §7 (Cross-Lifecycle Cascade Rules)
│   Touch: codified-rules.md → state-transitions.md §7
│
├── Cross-document consistency review
│   Read:  All documents in scope for the review
│   Produce: Structured gap report — see Consistency Review section below
│
└── Extending an existing section (adding content to an established domain)
    Read:  The specific document and section
    Touch: The document; check dependency table in @.agents/agents.md for propagation
```

---

## Invariant Authoring Rules

When adding a new invariant, confirm these before writing:

1. Check `@specification/invariants-catalogue.md` — is the proposed ID already in use?
2. New RINV, CINV, PINV, or TINV? Match the prefix to the domain.
3. Every invariant entry in `invariants-catalogue.md` requires all six columns: ID, Rule, Enforcement Layer, Enforcement Mechanism, Violation Behaviour, Spec Reference.
4. Enforcement Layer must be one of: `Schema`, `Service`, `Both`. No other values.
5. The same invariant must appear in `codified-rules.md` (as the rule) and `invariants-catalogue.md` (as the reference entry). Both must say the same thing.
6. If the invariant gates a state transition, the transition table in `state-transitions.md` must reference the invariant ID in its gate preconditions column.

---

## State Machine Authoring Rules

When adding or modifying a lifecycle:

1. Every lifecycle in `state-transitions.md` requires both a state machine diagram (ASCII) and a transition table. Neither alone is sufficient.
2. Diagram format: `[State] → [State] ⇄ [State]` using the arrow conventions from existing diagrams.
3. State names: Title_Case with underscores. No spaces, no hyphens.
4. Transition table columns: From, To, Gate Preconditions. Match exactly.
5. Every state must have at least one valid inbound and one valid outbound transition, or be explicitly documented as a terminal state.
6. If the lifecycle introduces a new `lifecycle_state` column value, update the enum in `data-model.md` for the relevant table.

---

## Data Model Authoring Rules

When adding or modifying tables:

1. Follow the existing table format exactly: column name, type, nullable (YES/NO), default, notes.
2. Every new FK relationship must be added to §9 (Foreign Key Relationship Map).
3. Every new schema-level constraint (CHECK, NOT NULL, UNIQUE) must be added to §10 (Schema-Level Constraint Summary).
4. Human-readable ID columns (e.g., `risk_id TEXT`, `tm_id TEXT`) follow the existing naming pattern for the domain.
5. All timestamps use `timestamptz` with `now()` default. No `datetime` or bare `timestamp`.
6. UUIDs use `gen_random_uuid()` as default for PKs.

---

## Consistency Review Format

When asked to perform a cross-document consistency review, produce output in this structure:

```
## Consistency Review — [Scope]

### PASS
- [Document A §Section] ↔ [Document B §Section]: [what matches and why it matters]

### GAP
- [Document A §Section] states [X]. [Document B §Section] states [Y].
  Correction: [which document should change and to what]

### MISSING
- [Element] present in [Document A] has no corresponding entry in [Document B].
  Addition required: [what needs to be added and where]

### EDITORIAL
- [Document] [location]: [violation — em dash / unverifiable claim / non-standard naming / etc.]
```

Do not mix categories. A GAP is a contradiction between two documents. MISSING is an omission in one document. PASS is explicit confirmation, not assumed.

---

## Editorial Checklist (Run on Every Output)

Before presenting any draft, verify:

```
□ No em dashes anywhere in the output
□ No quantitative claims that cannot be sourced to the repo's own specification
  or a named public framework
□ No employer-specific content, proprietary tool names, or internal framework references
□ All invariant IDs follow XINV-N format with correct prefix for the domain
□ All state names use Title_Case_With_Underscores
□ All new sections follow the structural pattern of the nearest equivalent existing section
□ Version header present on specification documents if a new document is being created
□ CC BY 4.0 licence footer present on new documents
□ DISCLAIMER.md referenced or linked where the document is a specification
  or architecture guide
```
