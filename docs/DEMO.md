# How to demo VertiBottle

A click-by-click sequence that shows the whole pipeline in about five
minutes. Do a dry run first: alerts fire on the simulator's schedule, so
step 4 sometimes needs a minute of patience (or the impatient variant below).

## Setup (before the audience arrives)

1. `./run.sh`, open http://127.0.0.1:8000.
2. Let it run 3–5 minutes so the charts have history and at least one
   alert cycle has happened.
3. Optional second browser window on `?auto=coordinator#/ussd` (the USSD phone),
   so you can switch fast.

## The walkthrough

**1. Overview (log in as `coordinator`, password `demo1234`).**
Five cards, one per pilot site: 3 schools, 2 community farms. Green means
every parameter is inside its crop's band. Point out the traffic-light
colours and the "Updated HH:MM:SS" line ticking every ~30 s — that's the
dashboard polling the API, per the spec.

**2. Pick a site — ideally an amber or red one.**
The **Live farm** panel comes first: water circulating up the column, the
pump turning, leaves swaying, the reservoir filled to the measured level
and tinted by nutrient strength, the sun as bright as the light reading.
Nothing is decorative — every moving part is reading live data. Below it,
seven charts with the crop's target band shaded green.

**3. Watch the escalation.**
When a value first leaves the band the site turns **amber — Watch** and
that subsystem starts pulsing amber in the farm view. One reading might be
probe noise; nobody gets paged. If the *next* reading is also out of band
the alert is raised and dispatched: the ribbon turns **red — Notification
sent**, the subsystem pulses red, and a banner appears at the top of every
relevant user's dashboard. Leave it alone for a minute and make the point:
the value *stays* broken. This problem does not fix itself.

**4. Show the multi-channel dispatch (as `admin`, Admin → Notification outbox).**
The same alert went out as a dashboard banner (real), plus email, SMS and
USSD messages — simulated, but with the exact text that would have been
sent, in the operator's language. Note the SMS format matches the SRS:
"VertiBottle ALERT: <site> pH 4.8 (target 5.5-6.5)…".

**5. Acknowledge, and watch the farm get fixed.**
This is the centrepiece. Hit **Acknowledge** on the ribbon and stay on the
page. The subsystem stops flashing red and the corrective action starts
playing: a misting head spraying for low humidity, a doser dripping for
pH, shade cloth unrolling over the reservoir for heat, the ventilation fan
spinning for hot air. The caption names what is happening ("Humidity:
misting the grow area — value returning to target") and the number beside
it climbs back toward the band in real time. The charts agree, because
it's the same data.

**6. Acknowledge from a feature phone (USSD page).**
The operator picker at the top of the phone defaults to an operator whose
language matches the dashboard — Aissatou (English) or Falmata (French) —
because a feature phone has no language toggle of its own. Press `2` to
see current alerts; dial again, `3`, then the alert number. Three presses,
per the usability requirement. Then jump back to that site and watch the
same fix animation play from a USSD acknowledgement.

**7. Resolution, hands-free.**
When the recovering value re-enters the band, the alert flips to
**Resolved** on its own — the system verified the corrective action
worked, and the farm view goes calm and green. As `coordinator` or
`admin`, close it from the Alerts page (Resolved → Closed). The Alerts
view now shows the full lifecycle history.

**8. Audit trail (as `admin`, Admin → Audit log).**
Every reading, every state change, every acknowledgement with the actor's
name, every threshold edit with old → new values. Append-only; there is no
edit or delete path, not even for admins.

**9. Close the loop on management (still `admin`).**
Register a new site (name, type, crop) — it appears on the overview with
live data within one simulator tick. Change a threshold and show the
tamper log entry appear in the audit view.

## The impatient variant

Alerts too rare during a live slot? Force one: as `admin`, edit a threshold
so the current value is outside it (e.g. set lettuce `ph_max` to 5.0 —
current pH sits near 6). Within two ticks (~20 s) you get Watch, then the
raised alert and notifications. Put the threshold back afterwards; both
changes land in the audit log, which is itself a nice beat in the story.

Or restart with hotter drift: `SIM_DRIFT_PROBABILITY=0.02 ./run.sh`.

## Reset to a clean slate

```bash
lsof -ti:8000 | xargs kill
/Applications/Postgres.app/Contents/Versions/latest/bin/dropdb vertibottle
./run.sh
```

Fresh sites, fresh users, empty audit log, data flowing within seconds.
