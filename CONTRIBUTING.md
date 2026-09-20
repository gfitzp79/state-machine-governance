# Contributing

This repository holds two things under two licences, and the contribution rules
differ accordingly.

| | What it is | Licence |
|---|---|---|
| Repository root | The framework: specification, architecture, methodology | [CC BY 4.0](./LICENSE) |
| [`platform/`](./platform) | The reference implementation, a working GRC platform | [Apache 2.0](./platform/LICENSE) |

---

## Contributing to the framework

The framework is a reference architecture derived from public-domain sources
(NIST SP 800-30, ISO 27005, FAIR, NIST RMF). It is deliberately opinionated, and
its structure is the point: changes that dilute the precision are not
improvements.

**Welcome without discussion:** typos, broken links, formatting, clarifications
that do not change meaning.

**Open an issue first:** new invariants, changes to a state machine, changes to
the scoring model, new domains. These have implementation consequences: every
rule in the specification is enforced in code, so a specification change is a
code change wearing different clothes.

**Not accepted:** vendor-specific content, proprietary or employer-specific
material of any kind, or framework content that cannot be traced to a public
standard.

If you have adapted the framework for your own organisation, that adaptation is
yours. CC BY 4.0 asks only for attribution. I would be glad to hear what you
changed and why, but you owe nothing back.

### The two speeds

The repository moves at two speeds on purpose, and knowing which one you are in
saves an argument later.

| | Framework (repository root) | Platform (`platform/`) |
|---|---|---|
| What it is | A published specification people cite and build against | Software |
| Licence | CC BY 4.0 | Apache 2.0 |
| Changes | Rarely, deliberately, discussed first | Continuously |
| Versioning | Per document, in its `**Version:**` line | Semantic, in `CHANGELOG.md` |
| Review | Maintainer, always. See [CODEOWNERS](./.github/CODEOWNERS) | Normal pull request review |

Static does not mean frozen. It means a change arrives as a proposal with a
reason rather than as a side effect of somebody fixing something else. A
specification that shifts under its readers is worth less than one that is
slightly wrong in a known way.

### How a framework improvement lands

Most improvements are found while building: a rule turns out to be unenforceable,
or two documents disagree, or the code needs something the specification never
said. That is the normal case, not a failure, and this is the route.

**1. Open an issue.** Name the rule, say what is wrong with it, and say what you
found that proves it. "TINV-4 says the foreign key targets `controls`, and the
schema targets `control_deployments`" is a complete issue.

**2. Agree the shape before writing it.** Framework changes fall into three
kinds, and they carry different weight:

- a **correction**, where the documents disagree with each other or with a
  public standard. No discussion needed beyond confirming the facts.
- an **extension**, which adds a rule without changing an existing one. Needs
  agreement that it belongs in the framework rather than in one deployment's
  configuration.
- a **change of meaning**, where an existing rule now says something different.
  Rare, and it invalidates work people have done against the old text. It needs
  a stated reason, a version bump, and a `CHANGELOG.md` entry that says plainly
  what is no longer true.

**3. Move every affected document together.** `codified-rules.md` is the source
of truth. `state-transitions.md`, `invariants-catalogue.md` and `data-model.md`
derive from it, and a pull request that updates one and not the others will fail
CI rather than be caught in review:

```bash
python tools/check_invariant_drift.py     # code and catalogue agree
python tools/check_spec_references.py     # every spec_ref points at a real section
python tools/check_em_dashes.py           # the editorial rule, enforced
```

**4. Enforce it or do not add it.** An invariant with no predicate behind it is
a sentence. If the rule cannot be checked, say so in the catalogue by giving it
an honest enforcement layer rather than an aspirational one.

**5. Record it.** Bump the document's `**Version:**` line and add an entry under
the framework heading in `CHANGELOG.md`. Somebody who adopted the framework six
months ago needs to be able to see what moved.

### What is configuration, not framework

Before proposing a framework change, check whether it is really a change to one
organisation's operating model. Appetite bands, SLAs, control families, role
definitions, taxonomies and framework catalogues all live in
`platform/config/governance.yml` and are marked `[CUSTOMISE]` in the
specification. Adding a value there is not a framework change and needs no
discussion.

The distinction is worth defending. The band *names*, the 1-5 scales, the CE
ratings and the treatment strategies are fixed, because invariants and `CHECK`
constraints reference them by name. Their boundaries and their contents are
yours.

---

## Contributing to the platform

### Licensing of contributions

By submitting a pull request against `platform/`, you agree that your
contribution is licensed under Apache 2.0, per section 5 of that licence. There
is no separate CLA.

Sign your commits off under the [Developer Certificate of
Origin](https://developercertificate.org/):

```bash
git commit -s -m "your message"
```

That adds a `Signed-off-by` line asserting you have the right to submit the work.

### Getting it running

Docker is the only prerequisite.

```bash
cd platform
cp .env.example .env
docker compose up -d
```

Then <http://localhost:8080>, signing in as `analyst@example.com` /
`changeme123`.

### Running the tests

Both suites must pass before a pull request is reviewed.

```bash
# config_test.py: 33 tests of the configuration layer. Fast, no database needed.
docker compose exec api python config_test.py

# smoke_test.py: 160 tests of gates, invariants, cascades, and direct-SQL bypass
# attempts. Mutates state deliberately, so it needs a freshly seeded database.
docker compose down -v && docker compose up -d
docker compose exec api python smoke_test.py
```

CI asserts those totals against what the suites report, so adding a test means
updating the figure here and in `platform/README.md`. Each one is written beside
its script name because that is how the check knows which suite a number claims
to describe; a bare total is refused rather than guessed at.

Both exit non-zero on failure. Neither uses a test framework yet: they are
plain scripts with a `check()` helper, which keeps the output readable as a
statement of what the platform guarantees. Migrating them to pytest is a welcome
contribution.

For frontend changes:

```bash
cd platform/frontend
npm install
npx tsc -b --noEmit    # must be clean
```

### The one architectural rule

**Every write goes through `LifecycleService`.** It runs the same four steps in
the same order: mutate, enforce invariants, cascade, audit. Routers never
touch the database session directly. A pull request that writes to the session
from a router, or mutates a lifecycle field without going through
`StateMachine.fire()`, will be asked to change.

This is not style. It is the reason the platform can claim a rule is enforced on
every path rather than on the paths someone remembered.

Concretely:

| Change | Where it belongs |
|---|---|
| A threshold, SLA, or taxonomy value | `platform/config/governance.yml`: never hardcoded |
| Which roles may fire a transition | `modules/<domain>/machine.py` |
| A new precondition on a gate | `modules/<domain>/machine.py` |
| A new hard rule | `modules/<domain>/invariants.py`, with a specification reference |
| Cross-entity propagation | `modules/cascades.py`, which is the only place one module reaches into another |
| A new domain | `models · machine · invariants · service · router` |
| A schema change | a model edit **and** an Alembic migration. `alembic check` runs in CI |

### Migrations

A model change without a migration is a schema the history no longer describes,
so `alembic check` fails the build.

```bash
docker compose exec api alembic revision --autogenerate -m "what changed"
```

Read what it generated. Autogenerate handles columns, constraints and indexes,
and is blind to the two things most likely to matter in this repository:

- **Triggers.** The append-only tables are enforced by trigger and autogenerate
  cannot see one. A migration adding an append-only table adds it to
  `APPEND_ONLY_TABLES` in `app/db_init.py` too, which is the authoritative list,
  and boot verifies every entry is really present before serving a request.
- **Data.** A column gaining `NOT NULL` needs a backfill you write yourself.

A `server_default` goes in as `func.now()` or `sa.text(...)`, never as a bare
string. A bare string is a literal: PostgreSQL evaluates it once while running
the DDL and freezes the result, which is how fifteen timestamp columns spent
0.1.0 recording the moment the schema was built instead of the moment the row
was written.

### Adding or changing a rule

Every invariant carries its specification reference. If you add one, the
specification gets the rule too: a rule enforced in code and absent from the
documents is exactly the drift this project exists to argue against. A pull
request adding an invariant should touch both
`specification/invariants-catalogue.md` and the module's `invariants.py`.

Every invariant also declares its enforcement layer. Declare `schema` only if
there is genuinely a `CHECK` constraint or trigger behind it; `both` only if
there are both. An overstated enforcement claim is worse than an understated one.

Two checks enforce this, and CI runs both:

```bash
python tools/check_invariant_drift.py
```

Every invariant registered in code appears in the catalogue with the same
enforcement layer, and vice versa. Add an invariant without a catalogue row and
the build fails.

```bash
python tools/check_spec_references.py
```

Every invariant's `spec_ref` points at a section of `codified-rules.md` that
actually exists. Four threat invariants once cited sections that had never been
written; a rule whose stated reason does not exist is the first rule somebody
removes.

### Code style

There is no formatter configured yet, so match the surrounding code:

- `from __future__ import annotations` at the top of every module
- Module docstrings explain *why* the module exists, not what it does
- String concatenation rather than f-strings in messages and SQL-adjacent code
- Type hints on public functions
- Comments explain reasoning, not mechanics: if a line needs a comment to say
  what it does, rename something instead
- British English in user-facing text and documentation
- No em dashes in markdown. Use a comma, a colon, or restructure the sentence.
  `python tools/check_em_dashes.py` runs in CI. Application code is exempt,
  because there an em dash is the empty-value placeholder in a table cell and a
  label separator rather than punctuation

### Pull requests

- One concern per pull request
- Say what rule or behaviour changed, and why
- Note any specification document that needs to change with it
- If you changed enforcement, say how you proved it, ideally a new `check()` in
  the smoke test

---

## Security

Do not open a public issue for a security defect. See [SECURITY.md](./SECURITY.md).

---

## Disclaimer

This repository is independent research and carries no affiliation with any
current or former employer of the author. See [disclaimer.md](./disclaimer.md).
Contributions are accepted on the same basis: do not submit anything you are not
free to license under the terms above.
