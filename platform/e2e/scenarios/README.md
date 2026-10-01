# Business scenarios

`smoke_test.py` proves each rule holds on its own, against seed data. This
harness proves something different: that the objects work together when a
real organisation drives them through their lifecycles.

It plays a mid-sized payments company launching a customer self-service portal.
Every object is created from nothing, by the person whose job it is, signed in
as that person:

| | Scenario |
|---|---|
| S1 | Register the portal and take a WAF control from Design to Operating |
| S2 | Threat model the portal from Scope to Active: mitigate, accept, promote, reference |
| S3 | The promoted risk from Intake to Monitoring, with a treatment that builds a second control |
| S5 | A policy from Draft to Active, revised, with two exceptions, one left to expire |
| S6 | The WAF evidences a NIST CSF requirement |
| S7 | The WAF fails its test: the cascade, then the repair |
| S8 | A Moderate risk is accepted by a VP, and the acceptance lapses |
| S9 | Closing and reopening a risk |
| S10 | Retiring controls |
| S11 | Deprecating a policy |
| S12 | Re-signing, deprecating and abandoning threat models |

Each step records one of four outcomes:

- **PASS**: the platform did what the specification says.
- **FAIL**: it did not. A refusal that should not happen, an acceptance that should have been refused, a crash, or a cascade that never fired.
- **GAP**: it did what the code says, but an organisation would be stuck, misled or forced into a workaround. A design question, not a defect.
- **NOTE**: an observation, neither right nor wrong.

## Running it

It mutates the database heavily, and needs a freshly seeded stack. From here:

```bash
./reset.sh
```

```bash
python scenarios.py
```

It exits non-zero on any FAIL. Results go to `results.json`. Pass a number to
run only the first N stages: `python scenarios.py 3`.

The only dependencies are the Python standard library and `docker compose`, used
to move the calendar for expiry scenarios (an exception lapsing, an acceptance
running out) by editing a date in the database. Nothing else is touched directly.

Environment overrides: `SMG_API` (default `http://localhost:8080/api`),
`SMG_DEMO_PASSWORD`, `POSTGRES_USER`, `POSTGRES_DB`.

## What it found

The first run against 0.2.0 checked 206 steps: 187 passed, 11 failed, and eight
were design gaps. Tracing the failures found 18 defects, fixed in the release
that added this harness and listed in `CHANGELOG.md`. Every FAIL was in the space
between objects, where a test of one rule never looks.
