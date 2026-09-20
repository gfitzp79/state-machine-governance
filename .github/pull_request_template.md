## What changed, and why

<!-- One paragraph. What rule or behaviour is different afterwards? -->

## Which part of the repository

- [ ] **Platform** (`platform/`): software
- [ ] **Framework** (root: `specification/`, `architecture/`, `methodology/`): the published specification
- [ ] Both

> A rule that changes in one has to change in the other. CI fails a PR that adds
> an invariant to the code without cataloguing it, or that cites a specification
> section nobody wrote. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## If this touches the framework

<!-- Delete this section for a platform-only change. -->

- [ ] There is an issue discussing it, agreed before the code was written
- [ ] The document's `**Version:**` line is bumped
- [ ] `CHANGELOG.md` records it under the framework heading
- [ ] Every affected document moved together: `codified-rules.md` is the source of
      truth, and `state-transitions.md`, `invariants-catalogue.md` and
      `data-model.md` derive from it

## Enforcement

- [ ] A new rule is enforced somewhere, not only described
- [ ] Its enforcement layer is stated honestly. `Schema` only where a `CHECK`,
      `NOT NULL`, foreign key or trigger genuinely exists
- [ ] There is a test that fails without the change

<!--
Do not paste CI output here. The pipeline runs, in this order:

  migrations applied and append-only triggers verified
  models and migrations agree (alembic check)
  a v0.1.0 database upgrades without losing data
  33 configuration tests, 147 enforcement tests
  endpoint posture and the boot guard
  published counts match the code
  links, em dashes, invariant drift, dangling specification references

Locally: `cd platform && docker compose up -d --wait`, then
`docker compose exec api python config_test.py` and `smoke_test.py`.
-->

## Sign-off

- [ ] Commits are signed off under the [DCO](https://developercertificate.org/)
      (`git commit -s`)
