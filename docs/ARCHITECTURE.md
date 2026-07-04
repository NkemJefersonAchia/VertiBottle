# VertiBottle architecture

This document walks the SRS's 11-step data flow (section 2.1) through the
actual code, then covers the class model, the alert state machine, and every
place the implementation deviates from the SRS design and why.

## The 11 steps, mapped to code

The SRS describes one reading travelling from a probe to the dashboard. In
this build the field and transport layers are simulated in software, but the
reading still passes through every backend stage a hardware reading would.

| # | SRS step | Where it lives here | Notes |
|---|---|---|---|
| 1 | Sensing | `backend/app/simulator.py`, `ChannelSim.next_value()` | Generates a plausible value per (site, parameter): wandering baseline, day-curve for air temp/light/humidity, sensor-accuracy noise from SRS 3.2, occasional out-of-band drift episodes. |
| 2 | Signal conditioning | folded into `ChannelSim` | The gaussian noise term stands in for ADC jitter; there is no analog electronics to condition. |
| 3 | Control (firmware loop) | `Simulator.run()` | The tick loop plays the role of the ESP32 wake schedule. Real cadence (5/15/30 min) is compressed to `SIM_INTERVAL_SECONDS` (default 10 s) so a demo is watchable. |
| 4 | Validation | `ChannelSim.next_value()` clamps physical floors | Real firmware discards out-of-range/disconnected-probe values; the simulator never produces them, so this stage is thin by construction. |
| 5 | Local buffering (SD card) | **not implemented** | Meaningless without hardware or a network that can fail. The schema doesn't preclude it: readings carry their own timestamps, so late-arriving buffered data would ingest cleanly. |
| 6 | Transmission (MQTT/TLS) | **replaced** by a direct function call | `Simulator.step()` writes `Reading` rows through the same session a paho-mqtt subscriber callback would use. Swapping in real MQTT means adding a subscriber that does exactly what `step()` does per message. |
| 7 | Ingestion | `Simulator.step()` + `models.Reading` | Validates site/node existence implicitly via FKs, stamps `last_seen` on the node (feeds FR 8.2 health), writes the reading and an audit row (FR 8.1). |
| 8 | Rule evaluation | `backend/app/rule_engine.py`, `evaluate()` | Runs synchronously right after each write, per SRS "immediately after a write". Fetches the site's crop band, decides Normal/Watch/Alert. |
| 9 | Alert routing | `backend/app/notifier.py`, `dispatch()` | Fans out to every active operator of the site: dashboard banner always; email/SMS/USSD per the operator's contact details. Enforces the 20-per-channel-per-site-per-day rate limit. |
| 10 | Visualization | `frontend/app.js` (`renderSite`, `bandPlugin`) | Polls `/api/v1/readings?site_id=…&hours=24` every 30 s, one Chart.js chart per parameter, target band shaded green, out-of-band badge in red. |
| 11 | Operator acknowledgement | `routers/alerts.py` (`/ack`), `routers/ussd.py` (option 3) | Dashboard button or USSD menu. Email-reply/SMS-reply ACK has no inbound channel to receive replies, so those paths exist only as message text. |

## Components

```
frontend (static)  ──HTTP──▶  FastAPI (backend/app/main.py)
                                │
        routers/ (API surface)  │   simulator.py (background task)
                                ▼        │ writes readings, ticks clock
                          SQLAlchemy ◀───┘
                                │              rule_engine.py ──▶ notifier.py
                                ▼                    │                │
                          PostgreSQL                 └── state_machine.py
                     (readings, alerts, audit…)          (legal transitions)
```

`state_machine.py` is deliberately the only place that knows which alert
transitions are legal. The rule engine, the alert endpoints, the USSD
handler and the timeout sweeper all call `transition()`; an illegal jump
raises instead of corrupting an alert's lifecycle.

## Class model vs. the SRS class diagram

Implemented in `backend/app/models.py`. Differences from Appendix B:

1. **User subclasses collapsed.** The diagram has Operator, Administrator,
   ProgrammeCoordinator and Agronomist extending User. They add behaviour
   but no persistent state, so the database uses one `users` table with a
   `role` enum. The behavioural differences live in `security.py` role
   checks. Joined-table inheritance would buy joins, not correctness.
2. **Dashboard is not a persisted class.** In the diagram it aggregates
   sites and displays readings; here that is the frontend plus the
   `/sites` and `/readings` endpoints. Persisting a Dashboard row would
   have stored nothing.
3. **Notification carries `recipient`, `message`, `status`.** The diagram
   only has channel/sentAt. Since email/SMS/USSD are simulated, the exact
   message text that would have been sent *is* the deliverable, so it is
   stored and shown in the admin outbox.
4. **Alert timestamps per state.** The diagram has `createdAt`; the
   implementation stamps `raised_at`, `notified_at`, `acknowledged_at`,
   `resolved_at`, `closed_at` so the audit story (and the NFR latency
   budgets) can be inspected per alert.
5. **CropProfile is shared by sites growing the same crop** (association
   is Site *→1* CropProfile as in the diagram). Consequence: editing
   thresholds affects every site on that crop. Acceptable at pilot scale
   (5 sites, 4 crops); per-site profile copies are the obvious v1.1 change
   and would only touch `seed.py` and the thresholds endpoint.

## Alert state machine as implemented

States and transitions are exactly the SRS diagram, plus one addition:

```
Normal ──▶ Watch ──▶ Alert Raised ──▶ Notification Sent ──▶ Acknowledged ──▶ Resolved ──▶ Closed
              │                              │                                              ▲
              │                              └── timeoutExpired ────────────────────────────┤
              └── recovered_in_watch (addition) ────────────────────────────────────────────┘
```

- "Normal" is not a row — no alert exists while readings are in band.
  A Watch row is created on the first out-of-band reading.
- **Addition — `Watch → Closed`** (`close_reason="recovered_in_watch"`).
  The SRS diagram starts tracking at Alert Raised and treats Watch as
  transient. Because this build persists the Watch stage (so the dashboard
  can go amber early), it needs a way to retire a Watch whose next reading
  came back in band: the single-spike false alarm the two-stage escalation
  exists to absorb. Without this edge, spike-Watches would accumulate forever.
- `timeoutExpired` is swept by the simulator loop every tick
  (`Simulator._sweep_ack_timeouts`, window = `ALERT_ACK_TIMEOUT_SECONDS`).
- A reading returning in band while an alert is in Notification Sent does
  **not** resolve it (there is no such edge in the SRS diagram, and an
  unacknowledged alert still needs a human). Resolution requires
  Acknowledged first; the rule engine then moves it to Resolved when it
  sees an in-band reading (`correctiveActionVerified`).

The full transition table is `TRANSITIONS` in `state_machine.py`;
`backend/tests/test_state_machine.py` pins every edge, legal and illegal.

## Where the NFR latency budgets stand

- **Reading → dashboard ≤ 30 s (NFR 1.1):** readings are committed
  synchronously each tick; the dashboard polls every 30 s. Worst case is
  one poll interval; no queue in between.
- **Reading → alert dispatched ≤ 60 s (NFR 1.2):** rule evaluation and
  notification dispatch run in the same transaction as the reading write —
  the latency is one function call, bounded well under a second. The design
  keeps this property even if ingestion moves to an MQTT consumer.

## Simulated vs. real, at a glance

| Piece | Status |
|---|---|
| Sensor nodes, MQTT, GSM/Wi-Fi | Simulated in `simulator.py` (see steps 1–6 above) |
| Rule engine, state machine, audit, RBAC | Real |
| Dashboard banner notifications | Real (poll-based) |
| Email / SMS / USSD-push | Stubbed: full message persisted with `status="simulated"`, shown in admin outbox |
| USSD interactive menu | Real logic, fake gateway (the phone-shaped page plays aggregator) |
| Auth | Real tokens + RBAC; PBKDF2 instead of the SRS's bcrypt-12, no 2FA — demo-grade on purpose |
| TLS 1.3, mTLS, HSTS (NFR 3.1) | Out of scope for localhost; nothing in the code assumes plaintext-only |
