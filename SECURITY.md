# Security Policy

This repository contains a governance and security platform. If it has a
vulnerability, the people most likely to be running it are the people least able
to absorb a surprise. Please report it privately.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting:**
[Report a vulnerability](https://github.com/gfitzp79/state-machine-governance/security/advisories/new)

That creates a private advisory visible only to the maintainers. Please do not
open a public issue for a security defect.

If private reporting is unavailable to you, open an issue titled
`Security contact request` with no technical detail, and a maintainer will
arrange a private channel.

### What to include

- What the defect is, and which component (`platform/backend`, `platform/frontend`,
  the container configuration, or the specification itself)
- The version or commit you tested
- Steps to reproduce, ideally against a clean `docker compose up -d`
- What an attacker gains
- Anything you have already tried as a mitigation

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement | 3 working days |
| Initial assessment and severity | 10 working days |
| Fix or documented mitigation for High and Critical | 30 days |
| Public advisory | After a fix ships, or 90 days, whichever is sooner |

This is a personal open-source project, not a vendor product. These are honest
targets rather than a contractual commitment, and I would rather state them and
occasionally miss than leave you guessing.

Credit is given in the advisory unless you ask otherwise.

## Scope

**In scope**

- Anything in `platform/`: the API, the UI, the container and nginx
  configuration, the governance configuration loader
- Authentication and authorisation defects, including any way to bypass a
  lifecycle gate, an invariant, or a role restriction
- Any route by which the database-layer immutability triggers or `CHECK`
  constraints can be circumvented
- A defect in the specification that would cause a correct implementation to be
  insecure

**Out of scope**

- The known limitations listed in [`platform/README.md`](./platform/README.md),
  which are documented rather than hidden: currently the local-password
  authentication default
- Findings that depend on the demo dataset, which is enabled only when
  `SEED_DEMO_DATA=true` and which the application refuses to combine with a
  non-development environment
- Missing hardening that the deployment documentation assigns to the operator,
  such as TLS termination
- Automated scanner output with no demonstrated impact

## Running it safely

This is a **reference implementation**. It is built to demonstrate that the
framework's rules can be enforced rather than described, and it has not been
through the operational hardening a production GRC system needs.

Before it holds real governance data:

- Generate a real `JWT_SECRET`. The application refuses to start on the shipped
  default unless `ENVIRONMENT` is explicitly set to development.
- Set `SEED_DEMO_DATA=false`. The demo dataset includes a published password and
  an account holding the `Admin` role.
- Terminate TLS in front of nginx.
- Replace local password authentication with your identity provider.
- Read the [AI tool lifecycle model](./architecture/ai-tool-lifecycle.md). It
  applies to this tool as much as to anything you build from the framework: a
  named owner before Build, prompt and application telemetry in the SIEM before
  Production, and defined decommissioning criteria.

## Supported versions

The project is pre-1.0 and has no release branches. Security fixes land on
`main`. Pin a commit if you need stability.
