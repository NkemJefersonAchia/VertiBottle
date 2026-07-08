# VertiBottle test strategy

135 automated tests, 95% branch coverage, running locally (`pytest`) and in
CI on every push (GitHub Actions). This document explains what is tested at
which level, why the overall approach is **grey-box**, and how the suite
applies the seven principles of testing (ISTQB).

## How to run

```bash
cd backend
../.venv/bin/python -m pytest tests -q                       # fast run
../.venv/bin/python -m pytest tests --cov=app --cov-branch   # with coverage
```

CI runs the same command with `--cov-fail-under=90` on every push and pull
request (`.github/workflows/ci.yml`), satisfying NFR 7.2 (automated tests on
every change, ≥80% branch coverage) and the SRS 2.5 constraint that all
changes pass CI. The suite runs on in-memory SQLite so CI needs no database
service; the dialect differences that shake out of that (see "defects found"
below) were themselves informative.

## Black, white or grey box?

**Grey-box, deliberately.** The two pure options don't fit this project:

- Pure black-box is impossible in spirit: the same person wrote the code
  and the tests, so "no knowledge of internals" would be a pretense. Worse,
  the riskiest logic (the alert state machine) has internal states that a
  purely external test can only reach slowly and non-deterministically —
  you'd wait for a simulator to drift out of band on its own schedule.
- Pure white-box would verify that the code does what the code does. It
  can't catch contract regressions: an endpoint renaming a JSON field
  passes every unit test and still breaks the dashboard and the USSD menu.

So the suite is layered, and each layer picks the lens that finds the most
defects there:

| Layer | Box | Files | What it knows |
|---|---|---|---|
| Unit: state machine, rule engine, notifier, simulator, security | **White** | `test_state_machine.py`, `test_rule_engine.py`, `test_notifier.py`, `test_simulator.py`, `test_boundaries.py`, `test_security.py` | Calls internal functions directly; asserts on internal state, transition tables, timestamps. |
| API/integration: every endpoint | **Black** | `test_api_*.py` | Only the HTTP surface. Asserts against docs/API.md and the SRS (status codes, JSON shapes, RBAC refusals, the 182-char USSD cap) with no reference to internals. |
| System/end-to-end: the full pipeline | **Grey** | `test_pipeline_e2e.py` | Forces a deterministic pH drift by reaching into the simulator's channel state (white knowledge), then observes and acts exclusively through the API as a user would (black behaviour): Watch → Alert → banner + outbox → acknowledge → recovery → Resolved → close → audit trail ordering. |

The grey-box compromise is what makes the e2e test both *deterministic*
(no waiting for random drift) and *honest* (every user-visible claim is
verified through the public interface).

## The seven principles, applied

**1. Testing shows the presence of defects, not their absence.**
Writing this suite found two real defects, which is the point:
- The rule engine relied on session autoflush to see a just-created Watch
  alert. The app's sessions run `autoflush=False`; production was masked
  only because the simulator commits every tick. Two out-of-band readings
  inside one transaction stacked 117 duplicate Watches and never escalated
  — no alert, no notification, silent failure of the product's core
  promise. Fixed with an explicit flush in `rule_engine.py` (the comment
  there credits the test).
- Timestamp arithmetic in the sites/health endpoints assumed
  timezone-aware datetimes; anything that returns naive ones (SQLite, and
  potentially other stores) crashed the traffic-light computation. Fixed
  with `ensure_utc()` in `models.py`.
A green suite doesn't prove correctness; these two bugs existed while the
app looked fine in a live demo.

**2. Exhaustive testing is impossible.**
Inputs are unbounded (any float per reading, any keypress string per USSD
session). Instead: equivalence partitioning and boundary-value analysis.
`test_boundaries.py` tests the band edges exactly — at `band_min`/`band_max`
(in-band, edges inclusive), one epsilon outside (Watch), and extreme values
— rather than "many" values. The USSD tests cover each menu branch and each
failure class (unknown phone, bad index, invalid choice, no site) rather
than all possible dial strings.

**3. Early testing (shift left).**
The alert lifecycle was specified as a transition table
(`state_machine.TRANSITIONS`) and unit-tested before any endpoint used it;
illegal-transition tests existed before the ack/close endpoints did. CI
runs on every push, so no change waits for a manual test pass. The two
defects under principle 1 were caught before any pilot user, which is the
cheapest they will ever be.

**4. Defects cluster together.**
Test effort is deliberately unequal. The rule engine + state machine +
alert endpoints get ~50 of the 135 tests because that's where the failure
modes concentrate (state, concurrency-adjacent logic, permission rules).
The audit read endpoint gets four. Both defects found so far were in the
predicted cluster (the reading→alert path), validating the allocation.

**5. Beware the pesticide paradox.**
The same assertions re-run forever stop finding new bugs. Countermeasures:
the simulator tests run scenario-style (forced-certain drift, forced-calm,
pathological internal states like a negative baseline) rather than one
golden path; the USSD length cap is asserted on *every* response in every
test via the shared `dial()` helper, so any new screen automatically gets
the check; and the regression rule is that every future bug fix lands with
a test that fails on the old code (both principle-1 defects have exactly
that).

**6. Testing is context dependent.**
This is a pilot-stage monitoring system where the crop dies if the
alert chain silently breaks, demoed on a laptop, with simulated hardware.
So: lifecycle correctness, RBAC and message contracts are tested
exhaustively; performance NFRs are *architecturally* satisfied (synchronous
dispatch, one poll interval) but not load-tested — meaningless against
SQLite on a laptop, and the SRS's 200-node year-one scale doesn't exist
yet. A payment system or the future actuator firmware (SRS 5.3) would
demand a completely different mix.

**7. Absence-of-errors is a fallacy.**
135 green tests wouldn't matter if a teacher can't tell what's wrong with
their farm. The suite is therefore paired with validation that tests
usefulness, not correctness: the scripted demo walkthrough
(docs/DEMO.md) exercises the real user journeys end to end in a browser,
and the headless-Chrome screenshots in the README are generated from the
running app, so the documented UI is the actual UI. The suite verifies we
built the system right; the walkthrough checks we built the right system.

## What is deliberately not automated

- **Frontend JS logic** (chart rendering, hash routing, i18n toggling).
  It's ~700 lines of vanilla DOM code; a JS test harness (Node, jsdom)
  would exceed the code under test. Mitigation: the API tests pin the
  contract the frontend consumes, the static-file tests ensure the assets
  ship, and the DEMO.md walkthrough covers the visual behaviour manually.
- **The live Postgres path** (TimescaleDB detection, pg8000 connection).
  Exercised by `run.sh` on every launch rather than by CI.
- **Load/performance** — see principle 6.

## Inventory

| File | Tests | Focus |
|---|---|---|
| `test_state_machine.py` | 7 | Every legal edge, every illegal jump, timestamp stamping |
| `test_rule_engine.py` | 9 | Watch/escalate/recover/resolve, channel independence, dedup |
| `test_boundaries.py` | 7 | Band-edge boundary values |
| `test_notifier.py` | 9 | SRS message formats EN/FR, fan-out, rate limit, inactive operators |
| `test_simulator.py` | 9 | Emission counts, heartbeats, audit-per-reading, drift, timeout sweep |
| `test_security.py` | 5 | Hashing, salting, malformed hashes, token uniqueness |
| `test_api_auth.py` | 9 | Login contract, all roles, 401s, audit |
| `test_api_sites.py` | 17 | Overview, traffic lights, registration RBAC, tamper-logged thresholds |
| `test_api_readings.py` | 6 | Series shape, CSV export + its RBAC |
| `test_api_alerts.py` | 13 | Ack/close happy paths and every refusal (403/404/409) |
| `test_api_notifications.py` | 8 | Banner feed scoping, mark-read, admin outbox |
| `test_api_ussd.py` | 19 | Full menu tree, 182-char cap, 3-press ack, language persistence |
| `test_api_admin.py` | 15 | Audit access + immutability, node health, operator management |
| `test_pipeline_e2e.py` | 1 | The whole SRS pipeline in one deterministic scenario |
