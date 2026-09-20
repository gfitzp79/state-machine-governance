# Changelog

This repository holds a framework and a reference implementation of it. They
version separately, because they change for different reasons.

- **The framework** (repository root: `specification/`, `architecture/`,
  `methodology/`) versions per document. Each carries its own version line.
- **The platform** (`platform/`) follows [semantic versioning](https://semver.org).

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Changed: three Phase 2 preconditions are derived, not attested

Found by using the tool rather than testing it. RINV-8 says all four Phase 2
preconditions must hold before scoring opens. Three of them were booleans a user
ticked, so what the rule actually required was that somebody had ticked four
boxes. A risk with no owner, no tier rationale and no linked control satisfied
"all stakeholders identified", "tier assigned with documented rationale" and
"control effectiveness assessed with evidence" by assertion alone. Demonstrated
against a running instance: `control_effectiveness_assessed` accepted `true`
with zero linked controls.

They are now read from the record:

- **RINV-8.2** needs the tier AND a non-empty `tier_rationale`, because the rule
  says "with documented rationale" and a rule that accepts an empty rationale is
  not asking for one.
- **RINV-8.3** needs the Risk Owner, Risk Stakeholder and Risk Analyst named.
  Treatment and control owners are named on those records, so they are checked
  where they live.
- **RINV-8.4** uses the same filters the scoring engine applies: an Operating
  objective with a deployment above CE-Unvalidated carrying evidence. A control
  the engine would refuse to score with is not an assessment.

`true_risk_confirmed` remains attested. Whether an item belongs in the register
is a judgement, and the record cannot supply it.

The three columns are dropped by migration `aaa34e5fc638`. Every risk write
model now sets `extra="forbid"`, so a client still sending a removed field is
told rather than silently ignored.

### Fixed: a gate report could describe the state before the write

Adding a threat scenario left the lifecycle panel saying "1 blocking: at least
one threat scenario identified" while the server's own gate report said the
transition was open. The relationship was already loaded, so the gate was
evaluated against the model as it was before the insert, and the UI stayed
wrong until the page was reloaded. `detail()` now refreshes before evaluating,
which is the one place this state reaches a client and therefore the one place
it cannot be forgotten.

### Fixed: a disabled control now says why it is disabled

The threat module already did this: `Accept locally` on a Critical scenario
carries `TINV-3` in its tooltip. The shared gate panel did not, so every
lifecycle in the product had a greyed-out Advance button with no explanation and
the user had to expand the gate to guess. The pattern existed; it was not
applied.

---

## [0.2.0] - Schema migrations and the compliance domain

### Added: schema migrations

- **Alembic owns the schema.** `alembic upgrade head` runs on every boot. This
  was the headline limitation of 0.1.0, which said in its own release notes that
  upgrading meant exporting data, recreating the schema and re-importing.
- **An 0.1.0 database is adopted, not replayed.** It was built by `create_all`
  and has no migration history, so replaying the initial migration against it
  would fail on the first `CREATE TABLE`. The first boot stamps it instead and
  carries on, leaving the data alone. `upgrade_test.py` exercises that path and
  runs in CI.
- **The initial migration installs the append-only triggers**, so
  `alembic upgrade head` on its own produces a correct database rather than one
  with `control_tests` that anybody can UPDATE.
- **Boot verifies the triggers are present** rather than assuming the statement
  that created them worked, and refuses to start if any is missing. Applying a
  control and evidencing it are different acts.
- `alembic check` runs in CI: a model changed without a migration is a schema
  the history no longer describes.

### Fixed: every timestamp default was frozen at schema-creation time

Fifteen columns declared `server_default="now()"` as a plain Python string.
SQLAlchemy treats that as a literal, so PostgreSQL evaluated it once while
running the DDL and stored the result as a constant. Every row written to
`control_tests`, `audit_log`, `policy_versions`, `threat_scenario_evidence`,
`treatment_checkins` and the link tables took the moment the schema was created
as its timestamp, not the moment it was written, unless the application happened
to set the value in Python.

`control_tests.tested_at` is the date an assessor reads when checking when a
control was last tested. It was the date the database was built.

Now `func.now()`, matching the `Timestamped` mixin that was always correct.
Proven by inserting a row two seconds after the seed and confirming the
timestamp advanced.

### Added: Compliance and Assurance (Domain 8)

- **Requirements are records, not framework names.** §15 CF-2 had controls
  inherit compliance mappings from linked policies, which cannot say *which*
  clause a control satisfies, and left CF-3's promise of gap detection
  unkeepable: a gap cannot be found without the set to compare against.
- **Coverage is asserted against a live control.** A requirement is Covered only
  while a satisfying control is Operating and deployed inside the framework's
  declared scope (AINV-2): TINV-4's argument applied to compliance.
- **§24.3, the cascade that makes it more than a mapping table.** A control
  entering Failure revokes every compliance position that rested on it, unless
  another Operating control still satisfies the requirement.
- **Licensing enforced, not documented (AINV-6).** ISO 27001, CIS, PCI DSS and
  the AICPA criteria ship as framework records with zero requirements, and the
  loader refuses at boot any catalogue declaring `redistributable: false` while
  carrying requirement text. NIST CSF 2.0 ships complete, all 106 subcategories.
  `tools/import_framework.py` loads licensed content into the database, never
  back into the tree.
- **Control attributes** an assessor actually asks for: objective statement,
  automation level, implementation type, operating frequency, assurance method,
  key-control flag; procedure reference, tooling and evidence type on the
  activity. CINV-11 caps CE by automation level, so a manual control cannot buy
  the likelihood reduction of an enforced one under RINV-9.
- `Cascade` added as a fourth enforcement layer in the invariants catalogue.
- Specification: `codified-rules` Part 6 (§21-24), `state-transitions` §9,
  `data-model` Domain 8. 11 new invariants, all catalogued and cross-referenced.

### Fixed

- **Nested cascades lost their effects.** A handler calling `cascades.emit` built
  a new event, so everything the downstream handlers recorded was discarded when
  it returned. The work still happened, so nothing looked broken; the audit trail
  simply stopped mentioning it.
- **Every control write model silently dropped unknown fields**, so the new
  attributes were unreachable through the API and a `PATCH` setting one returned
  200 having done nothing. Control write models now refuse extra fields.

---

## [0.1.0] - First public release

The first release of the reference implementation, alongside the specification
changes needed to describe what it actually does.

> **Why 0.1.0 and not 1.0.0.** There is no schema migration path yet: the schema
> is created by `create_all` on first boot, so upgrading between versions means
> exporting data, recreating the schema and re-importing. A 1.0 declares that
> upgrades are safe, and they are not yet. See *Known limitations* in
> [platform/README.md](./platform/README.md).

### Added: platform

- **The engine.** Domain-agnostic primitives: `StateMachine` for declarative
  gated lifecycles, `InvariantRegistry`, a deterministic 5×5 `ScoringEngine`,
  `CascadeBus` for in-transaction propagation, and `AuditTrail`.
- **One write path.** `LifecycleService` runs mutate → enforce invariants →
  cascade → audit, in that order, in one transaction. Routers never touch the
  session, which is what lets the platform claim a rule holds on every path
  rather than on the paths someone remembered.
- **Seven domains**: identity, risk, control, treatment, policy, threat
  management, and the scheduled jobs that carry the time-based invariants.
- **8 state machines, 53 gated transitions, 46 invariants, 24 cascade events.**
- **Configuration as the operating model.** Everything the specification marks
  `[CUSTOMISE]` lives in `config/governance.yml`, bind-mounted and strictly
  validated at boot. Appetite bands, SLAs, role definitions, control families,
  CE ceilings and the threat taxonomy are configuration; the band *names* and
  the 1–5 scales are fixed, because invariants and `CHECK` constraints reference
  them by name.
- **Append-only tables enforced by database trigger**, not by convention:
  `audit_log`, `risk_phase_history`, `policy_versions`, `control_tests`,
  `treatment_checkins`, `threat_scenario_evidence`.
- **Threat modelling connected to GRC in both directions.** A scenario is
  Mitigated only while the control deployment that mitigates it is operating;
  when that deployment fails the scenario re-opens and the model loses its
  sign-off. When a threat is mitigated, every risk record carrying it becomes
  eligible for re-evaluation. Neither direction moves a score on its own.
- **Environmental context for threat models**, read-only by construction: the
  control coverage and risk posture of the asset a model sits on, classified
  using the same filters the scoring engine applies. Informative, never
  determinative (TINV-7).
- **Interactive threat scenarios**: threaded comments, append-only evidence,
  status changes that require a rationale, and links to existing risk records
  that resolve a scenario without duplicating the register (TINV-8).
- **Component decomposition attributes**: data classification, data types,
  trust zone, exposure, and the asset a component actually sits on.
- `docker compose up -d` and a browser. Docker is the only prerequisite.

### Added: framework

- **`codified-rules.md` §19.4**, *Environmental Context*: the LKH-3 analogue for
  threat modelling. Identification runs against the architecture as designed,
  not as currently defended, so a well-controlled system does not look
  threat-free and the record of a threat survives the control that covered it.
- **`codified-rules.md` §19.5**, *Risk Register Linkage*: linking and promoting
  as distinct operations, plus the scenario working record.
- Component decomposition taxonomy in §19.1.
- **`state-transitions.md` §8**, the Treatment state machine, previously
  undocumented.
- `tools/check_invariant_drift.py` and `tools/check_spec_references.py`, both
  wired into CI: an invariant enforced in code and absent from the documents now
  fails the build.

### Fixed: framework

- §20.3 sat outside its code fence, and the stray fence that followed swallowed
  the `APPENDICES` heading and Appendix A.
- The invariants catalogue listed 33 of 46 invariants, and overstated the
  enforcement layer on twelve of them.
- TINV-4's foreign key targets `control_deployments`, not `controls`.
- `data-model.md` described a flat `controls` table, contradicting the
  three-level hierarchy in `codified-rules.md` §8.1, and used a CE vocabulary
  (`CE-Effective`/`CE-Partially`/`CE-Ineffective`) that no longer existed.
- CINV-7 was attributed to `risk_phase_history`; it is the control-testing
  immutability rule and attaches to `control_tests`.
- Two contradictions in `state-transitions.md`: Planned → Active required a CE
  that DL-2 makes unassessable, and Implementation → Operating demanded *all*
  deployments while citing an invariant that requires one.
- PINV-3 and PINV-7 cited §14.1, which did not exist.

### Fixed: platform

- The API client had no network-failure path. `fetch` rejects rather than
  resolving when the API is unreachable, and nginx answers a dead upstream with
  an HTML 502 that `JSON.parse` throws on. Neither produced an `ApiError`, and
  pages discard anything that is not one, so a stopped API left the sign-in
  button dead with no message.
- The Content-Security-Policy blocked the theme bootstrap inlined in
  `index.html`. A saved dark-mode preference was not merely ignored on load; it
  was overwritten with `light` on mount. Moved to `public/theme-init.js`.

### Security

- **The application refuses to start** with a shipped default `JWT_SECRET`
  unless `ENVIRONMENT` is explicitly `development`. Documentation is a policy;
  refusing to boot is the control.
- Demo seeding, which includes a published password and an `Admin` account, is
  refused outside a development environment.
- Fifteen engine and configuration endpoints that were anonymously readable now
  require authentication. They carry no record data, but machine definitions
  describe which roles may fire which gate: the separation-of-duties design.
- The nginx `/assets/` location declared its own `add_header`, which silently
  dropped every security header for the entire JavaScript bundle. Added CSP and
  Permissions-Policy, and `server_tokens off`.
- Both containers run unprivileged.

[Unreleased]: https://github.com/gfitzp79/state-machine-governance/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/gfitzp79/state-machine-governance/releases/tag/v0.2.0
[0.1.0]: https://github.com/gfitzp79/state-machine-governance/releases/tag/v0.1.0
