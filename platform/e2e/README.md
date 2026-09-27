# Recorded user journeys

What a control test changes, and where it stops. Four journeys through the real
UI, each recorded as a video with captions. They are tests first: every caption
is backed by an assertion on what the screen shows, so a video can only be
produced by a platform that behaves the way the caption says.

The scenario they share is specified in
[codified-rules §25](../../specification/codified-rules.md#25-scope-aware-test-impact).
CTL-006, a multi-factor authentication control, runs on five assets. PCI DSS
scopes three of them and is configured `all_in_scope`; ISO 27001 scopes all
five and is `any_in_scope`. Checkout Web sits inside both.

| Journey | What it shows |
|---|---|
| 1. Operating failure on Checkout Web | PCI DSS 67% to 0%, ISO 27001 unchanged at 75%. Only RISK-006, whose scope includes Checkout Web, is affected, with a proposed residual above appetite. The requirement owner and the posture floor alert fire; nothing about ISO does. |
| 2. Remediation retest | A passing retest with evidence returns Checkout Web to Active through DL-4. Coverage does not return by itself: its owner is told it can, and re-asserts it through the AINV-11 gate. |
| 3. Design failure, for contrast | The same control failing by design enters Failure everywhere. ISO 27001 falls to 25%, and every linked risk freezes regardless of scope. |
| 4. Test campaign | Four of five deployments tested, one failure. The population per framework names HR Portal as untested, and each owner receives one digest rather than one alert per cascade. |

## Running them

The journeys drive a running stack and reset its database before journeys 1,
3 and 4. Journey 2 continues from the state journey 1 leaves.

```bash
cd platform
docker compose up -d
cd e2e
npm install
npx playwright install chromium
npx playwright test
```

Videos and a screenshot per step land in `test-results/`.

| Variable | Default | Purpose |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8080` | Where the UI is served |
| `E2E_PROJECT` | `platform` | The docker compose project `reset-demo.sh` resets |
| `E2E_FAST` | unset | Set to `1` to drop the reading pauses for a quick functional run |

## The demo data

`reset-demo.sh` rebuilds the stack on an empty database, lets the standard seed
run, then applies `seed_scope_demo.py` on top. ISO 27001 and PCI DSS text is not
redistributable (AINV-6), so the demo imports requirement identifiers only, and
every title is the demo's own paraphrase, prefixed "Demo label". None of it is
the standards' wording.
