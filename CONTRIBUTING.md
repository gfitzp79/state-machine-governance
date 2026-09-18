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
the scoring model, new domains. These have implementation consequences — every
rule in the specification is enforced in code, so a specification change is a
code change wearing different clothes.

**Not accepted:** vendor-specific content, proprietary or employer-specific
material of any kind, or framework content that cannot be traced to a public
standard.

If you have adapted the framework for your own organisation, that adaptation is
yours. CC BY 4.0 asks only for attribution. I would be glad to hear what you
changed and why, but you owe nothing back.

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
# 33 tests: the configuration layer. Fast, no database needed.
docker compose exec api python config_test.py

# 147 tests: gates, invariants, cascades, and direct-SQL bypass attempts.
# Mutates state deliberately, so it needs a freshly seeded database.
docker compose down -v && docker compose up -d
docker compose exec api python smoke_test.py
```

Both exit non-zero on failure. Neither uses a test framework yet — they are
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
the same order — mutate, enforce invariants, cascade, audit — and routers never
touch the database session directly. A pull request that writes to the session
from a router, or mutates a lifecycle field without going through
`StateMachine.fire()`, will be asked to change.

This is not style. It is the reason the platform can claim a rule is enforced on
every path rather than on the paths someone remembered.

Concretely:

| Change | Where it belongs |
|---|---|
| A threshold, SLA, or taxonomy value | `platform/config/governance.yml` — never hardcoded |
| Which roles may fire a transition | `modules/<domain>/machine.py` |
| A new precondition on a gate | `modules/<domain>/machine.py` |
| A new hard rule | `modules/<domain>/invariants.py`, with a specification reference |
| Cross-entity propagation | `modules/cascades.py`, which is the only place one module reaches into another |
| A new domain | `models · machine · invariants · service · router` |

### Adding or changing a rule

Every invariant carries its specification reference. If you add one, the
specification gets the rule too — a rule enforced in code and absent from the
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
- Comments explain reasoning, not mechanics — if a line needs a comment to say
  what it does, rename something instead
- British English in user-facing text and documentation

### Pull requests

- One concern per pull request
- Say what rule or behaviour changed, and why
- Note any specification document that needs to change with it
- If you changed enforcement, say how you proved it — ideally a new `check()` in
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
