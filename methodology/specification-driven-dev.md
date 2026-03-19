# Specification-Driven Agentic Development: The Methodology

**Version:** 2.0-template | **License:** CC BY 4.0
**Purpose:** The methodology for building governance platforms using AI agents directed by precise specifications. Covers philosophy, the four-phase workflow, the artefact set, failure modes, and how the methodology scales to a team.

> **Core thesis:** The bottleneck for secure governance tooling is not syntax. It is the specification.

---

## 1. Philosophy

A discipline for directing AI agents to build governance platforms from precise specifications. The human designs the architecture, defines the invariants, and makes every structural decision. The agent generates code against those constraints.

This is not prompt engineering. Prompt engineering optimises how you talk to a model. This methodology optimises what you tell it to build and how you verify it built the right thing. The failure mode is almost never "the agent didn't understand me." It is "I didn't constrain the problem precisely enough."

### The practitioner profile

The methodology requires simultaneous fluency in three domains:

- **Engineering:** State machine design, schema modelling, RBAC enforcement, migration strategy, debugging pattern recognition
- **Architecture:** Option analysis, dependency management, cloud deployment as a day-one constraint, cost modelling
- **GRC:** Framework translation to code, scoring integrity, separation of duties, escalation design, regulatory alignment

A pure GRC person produces policy documents, not platforms. A pure engineer builds a database that works but misses governance semantics. The intersection is the capability that makes this productive.

### The build-vs-fix decision

**Fix the specification when:** The agent built something structurally wrong, made an unconstrained architectural decision, multiple components are affected, or the error would recur on rebuild.

**Debug the code when:** A narrow implementation bug in a single component, the spec is correct but the interpretation has a localised flaw, and the fix doesn't introduce architectural drift.

Early in the build, almost every failure is a specification gap. Later, as the spec matures, more failures are localised bugs.

---

## 2. The Four-Phase Workflow

### Phase 1: Codify

Transform your governance framework into a machine-readable rule set, entirely offline before any agent interaction: object states and transition rules, entity relationships as FK constraints, thresholds and scoring formulae, hard invariants, and acceptance criteria per module.

**Quality gate:** Reviewable by another GRC practitioner without reference to any code.

See: [Codified Rules Specification](../specification/codified-rules.md)

### Phase 2: Specify

Produce a standard artefact set per module: data model, architecture document, security invariants list, module breakdown with acceptance criteria, tech stack decision record, and persistent agent briefing.

**Quality gate:** A different practitioner could take over the build using only these documents.

### Phase 3: Build

Execute a strict prompt cycle. Each prompt is self-contained with schema context, business logic, and an explicit Definition of Done. Pass: pin and advance. Fail: revert, fix the spec, rebuild.

See: [Prompt Cycle](./prompt-cycle.md) for architectural guidance on prompt design and sequencing.

### Phase 4: Validate and Pin

Validation is "does the architecture match the intent," not "does it run." Extract the data structure at each inflection point and validate against the specification.

See: [Context Management](./context-management.md) for the extraction pattern and re-grounding discipline.

---

## 3. The Artefact Set

The artefact set is the build specification. The agent consumes it. The practitioner maintains it.

| Artefact | What the Agent Uses It For |
|---|---|
| **Data model** | Generates CREATE TABLE, migrations, ORM definitions. Ambiguous models → unintended FK decisions. |
| **Architecture document** | Understands module boundaries. Without boundaries, agent refactors across modules and introduces coupling. |
| **Security invariants list** | Constraint set. If an invariant is absent, agent has no reason to enforce it. |
| **Module breakdown** | Scopes each prompt. Without this, prompts are open-ended and outputs unpredictable. |
| **Tech stack decision record** | Selects libraries and patterns. Without explicit decisions, agent defaults to training distribution. |
| **Persistent agent briefing** | Re-grounding mechanism at session start. Prevents drift. See [Context Management §3](./context-management.md#3-the-re-grounding-mechanisms). |

---

## 4. Sequential Constraint Discipline

The agent receives no freedom to improvise. Each phase is completed and validated before the next opens.

| Phase | Provided | Blocked From |
|---|---|---|
| **Schema** | Full relational schema with FKs, joins, lifecycle enums | Writing application logic before schema is locked |
| **State machine** | Lifecycle with transitions, invariants, scoring formulae | Improvising business logic. Deviation = spec violation. |
| **Architecture** | Stack, RBAC model, deployment model | Making infrastructure decisions independently |

Schema first because everything depends on the data model. State machine second because business logic defines API enforcement. Architecture third because deployment constrains packaging but should not influence governance logic.

---

## 5. Failure Modes

Two failure modes observed in practice. Both resolved by fixing the specification, not the code.

**Circular Dependency:** Scoring engine and CE calculation called each other recursively. Root cause: spec didn't define computation order. Fix: CE resolves first as a fixed input. See [Scoring Model §9](../specification/scoring-model.md#9-fk-dependencies).

**Silent Gate Removal:** Agent removed a governance gate to resolve a rendering conflict. Component worked; invariant was absent. Root cause: spec didn't declare the invariant inviolable at code layer. Fix: declared it inviolable; no rendering requirement can justify removing a gate.

**The correction protocol:** (1) Identify the spec gap. (2) Update the constraint document. (3) Clear agent context. (4) Rebuild affected components only.

---

## 6. Scaling to a Team

| Role | Owns | Consumes |
|---|---|---|
| **GRC Architect** | Codified rules, invariants, scoring model, state transitions | Architecture doc (reviews) |
| **GRC Engineer** | Architecture doc, module breakdown, tech stack, agent briefing | Codified rules (builds against) |
| **Risk Analyst / SME** | Acceptance criteria, test scenarios, regulatory validation | Module outputs (tests) |

What doesn't change with team size: the specification is always the source of truth, the correction protocol is always "fix the spec," the agent briefing is always current, invariants are always schema or service-layer enforced, and phase transitions are always API-gated.

---

*Released under CC BY 4.0. Adapt freely with attribution.*
