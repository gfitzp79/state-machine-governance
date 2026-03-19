# Context Window Management: Preventing Architectural Drift

**Version:** 3.0-template | **License:** CC BY 4.0
**Purpose:** Strategies for managing context window degradation across agentic build sessions. Covers why context degrades, how to detect it, the re-grounding mechanisms, and the inflection point discipline that keeps multi-session builds coherent.

> **Core problem:** AI agents do not have persistent memory across sessions. Within a session, context quality degrades as the conversation grows. This is a constraint to be managed, not a bug to be fixed.

> **⚠ Cost awareness:** Re-grounding has a cost. For self-hosted agents, it is time (starting a new session, reloading context). For agentic SaaS platforms, it is credits (re-establishing project context consumes the same credits as building). Accept this cost. The cost of not re-grounding (drift that compounds across modules, producing rework later) is consistently higher.

---

## 1. Why Context Degrades

**Within a session:** As the context window fills, older content receives less attention. Early architectural decisions fade. Recent output biases future output. Invariant awareness decays. The agent's internal model of the schema diverges from reality.

**Across sessions:** Each new session starts with zero memory. The agent has no knowledge of what was built, what decisions were made, or which invariants have been enforced. Without re-grounding, each session is independent and potentially inconsistent.

---

## 2. GitHub-Connected Builds: What Changes and What Doesn't

If you are using the GitHub-connected operating model described in [deployment-saas.md](../architecture/deployment-saas.md), one category of context drift is mitigated: the agent builds against the live codebase in the connected repository rather than a snapshot held in context. This reduces the risk of the agent re-implementing existing components or contradicting schema decisions it cannot see.

**What the GitHub connection mitigates:**
- Agent re-implementing components that already exist in the codebase
- Agent making schema changes inconsistent with the committed data model
- Undetected schema modifications: every agent-generated change is a visible commit

**What the GitHub connection does not mitigate:**
- Session-level context window degradation: within a session, the agent still loses awareness of early decisions as context fills
- Invariant decay: the agent can still generate code that violates invariants if those invariants are not present in the active context
- Cross-module coherence: the agent does not automatically understand relationships between modules unless they are loaded into context
- Briefing file staleness: an outdated briefing file causes the same drift regardless of GitHub sync status

**Conclusion:** The GitHub-connected model reduces operational overhead and removes one class of drift, but does not replace the re-grounding discipline. All inflection point and session management practices below apply to both operating models.

---

## 3. Detecting Degradation

| Symptom | Meaning | Action |
|---|---|---|
| Agent re-implements existing components | Lost awareness of prior work | New session with updated briefing |
| FK references to non-existent tables | Schema model has drifted | Extract schema, re-ground |
| Previously enforced invariant violated | Invariant fell out of context | Reload invariants, rebuild component |
| Responses become verbose and generic | Compensating for lost context | Context saturated. Fresh session. |
| Proposes changes to stable components | Doesn't know they're pinned | Briefing needs "do not touch" list |
| Cross-module logic conflicts | Cross-module coherence degraded | Full extraction and validation |

**Critical distinction:** A bug is wrong output from correct context (fix the code or spec). Degradation is wrong output from lost context (re-ground).

**GitHub-connected note:** If the agent proposes a schema change that conflicts with the committed data model, this is a reliable degradation signal. The commit history provides the ground truth for comparison.

---

## 4. The Re-Grounding Mechanisms

### Mechanism 1: Persistent Agent Briefing

A living document read at session start. Contains: current build state, active schema summary, active invariants, explicit prohibitions, tech stack, known issues.

**Maintenance rule:** Update before every session, not after. The briefing reflects the world the agent is about to enter.

Full briefing specification: [Specification-Driven Development §3](./specification-driven-dev.md#3-the-artefact-set)

### Mechanism 2: Specification Artefacts

The codified rules, invariants catalogue, data model, and state transitions are external memory that doesn't degrade. Reference specific sections in prompts. When output drifts, redirect to the artefact.

### Mechanism 3: Extraction and Validation

At regular intervals, pull the current build state out of the agent's environment and validate against the specification independently. See §5.

**GitHub-connected enhancement:** The committed codebase is always available as an extraction source. Pull the current schema DDL, API gate implementations, and RBAC middleware directly from the repository rather than from the agent's environment. This produces a more reliable extraction than querying the agent's output.

---

## 5. Inflection Points

Certain moments require a full re-grounding because drift risk is highest.

**What triggers one:**
- Schema change (new table, column, constraint, FK)
- New module start (dependencies on prior modules)
- Scoring engine build (depends on data from multiple entities)
- Cascade implementation (connects multiple state machines)
- Post-failure rebuild (after any correction protocol cycle)

**What to do:**
1. Extract current data model, API endpoints, state machines from the build
2. Compare against specification artefacts
3. Document discrepancies: intentional design decisions vs. unintended drift
4. Update briefing to reflect current true state
5. Start new session with updated briefing
6. Pin current state before proceeding

**GitHub-connected workflow at inflection points:**
1. Pull current schema DDL and key implementation files from the GitHub repository
2. Compare against specification artefacts (not against the agent's last output)
3. Document discrepancies
4. Update briefing
5. Start new session — the agent will build against the committed codebase
6. Commit a clean state tag to the repository before proceeding

**The cost of skipping:** A wrong column constraint caught at the inflection point costs 15 minutes. Caught three modules later, it costs hours of rework.

---

## 6. The Extraction Pattern

Pull the build state out and validate independently.

| Extract | Validate Against |
|---|---|
| Database schema (DDL / migrations) | [Data Model](../architecture/data-model.md) |
| State machine implementation (API gate code) | [State Transitions](../specification/state-transitions.md) |
| Scoring engine (CE resolution path) | [Scoring Model](../specification/scoring-model.md) |
| RBAC middleware | [Reference Architecture §5](../architecture/reference-architecture.md) |
| Invariant enforcement (trace each code path) | [Invariants Catalogue](../specification/invariants-catalogue.md) |

**Frequency:** At every inflection point (minimum). After each major module (recommended). Before any build depending on prior session output (always).

**Discrepancies:** Intentional → update spec to match reality. Drift → revert to last pin, fix spec, rebuild.

**GitHub-connected note:** For the GitHub-connected model, extraction pulls directly from the repository. For the platform-native model, extraction requires querying the agent's environment or using the platform's export function. The GitHub model produces more reliable and complete extraction output.

---

## 7. Session Management

**Start a new session when:**
- Any inflection point (§5)
- Any degradation symptom (§3)
- Session exceeds ~20-30 substantial prompts
- Switching between modules
- After any failure/correction cycle

**Carry into new session:** Updated briefing, current prompt with full context, extraction outputs.

**Do not carry:** Entire prior conversation history (this is the degraded context), debugging threads, prompts from resolved components.

**Rule of thumb:** If the agent's output quality has visibly declined from session start, the session is too long.

**GitHub-connected session start:** Begin each new session by confirming the agent has context awareness of the current repository state. Reference key committed files in the opening prompt if the module being built has dependencies on prior work.

---

## Checklist

**Before every session:**
```
□ Briefing updated to current build state
□ Current module's spec artefacts accessible
□ Active invariants identified and included
□ Prohibitions listed
□ Last pin identified and stable
□ [GitHub-connected] Repository state confirmed as expected starting point
```

**At every inflection point:**
```
□ Build extracted (schema, gates, scoring, RBAC)
□ [GitHub-connected] Extraction pulled from repository, not agent output
□ Validated against specification
□ Discrepancies classified and resolved
□ Briefing updated
□ New session started
□ Current state pinned
□ [GitHub-connected] Clean state tagged in repository
```

**When degradation appears:**
```
□ Stop prompting immediately
□ Do not send "fix" prompts
□ Extract and validate
□ New session with fresh briefing
□ Continue from last pin
□ [GitHub-connected] Verify repository state matches expected last-good commit
```

---

*Released under CC BY 4.0. Adapt freely with attribution.*
