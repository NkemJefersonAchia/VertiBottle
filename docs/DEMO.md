# How to demo VertiBottle

A click-by-click sequence that shows the whole pipeline in about five
minutes. Do a dry run first: alerts fire on the simulator's schedule, so
step 4 sometimes needs a minute of patience (or the impatient variant below).

## Setup (before the audience arrives)

1. `./run.sh`, open http://127.0.0.1:8000.
2. Let it run 3–5 minutes so the charts have history and at least one
   alert cycle has happened.
3. Optional second browser window on `?auto=cb_op#/ussd` (the USSD phone),
   so you can switch fast.

## The walkthrough

**1. Overview (log in as `coordinator`, password `demo1234`).**
Five cards, one per pilot site: 3 schools, 2 community farms. Green means
every parameter is inside its crop's band. Point out the traffic-light
colours and the "Updated HH:MM:SS" line ticking every ~30 s — that's the
dashboard polling the API, per the spec.

**2. Pick a site — ideally an amber or red one.**
Seven live charts, one per parameter. The light-green band is the crop's
target range; the line drifting outside it is the simulated Far-North
afternoon doing its work. The number in the corner is the latest reading:
green when in band, red when out.

**3. Watch the escalation.**
When a value first leaves the band the site turns **amber — Watch**. One
reading might be probe noise; nobody gets paged. If the *next* reading is
also out of band the alert is raised and dispatched: the ribbon turns
**red — Notification sent**, and a banner appears at the top of every
relevant user's dashboard.

**4. Show the multi-channel dispatch (as `admin`, Admin → Notification outbox).**
The same alert went out as a dashboard banner (real), plus email, SMS and
USSD messages — simulated, but with the exact text that would have been
sent, in the operator's language. Note the SMS format matches the SRS:
"VertiBottle ALERT: <site> pH 4.8 (target 5.5-6.5)…".

**5. Acknowledge from a feature phone (USSD page).**
Dial with `+237650000002` (Falmata, the Makabay cooperative operator —
menus come up in French because that's her profile language). Press `2`
to see current alerts; dial again, `3`, then the alert number. Three
presses, per the usability requirement. If her site has no alert right
now, acknowledge from the dashboard ribbon instead as `school_op`.

**6. Resolution, hands-free.**
Back on the site page: when the drifting value returns to the band, the
acknowledged alert flips to **Resolved** on its own — the system verified
the corrective action worked. As `coordinator` or `admin`, close it from
the Alerts page (Resolved → Closed). The Alerts view now shows the full
lifecycle history.

**7. Audit trail (as `admin`, Admin → Audit log).**
Every reading, every state change, every acknowledgement with the actor's
name, every threshold edit with old → new values. Append-only; there is no
edit or delete path, not even for admins.

**8. Close the loop on management (still `admin`).**
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
