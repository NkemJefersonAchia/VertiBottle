# VertiBottle API guide

Base URL: `http://127.0.0.1:8000/api/v1`. Everything is JSON. Interactive
OpenAPI docs live at `/docs`; this is the written version for people who
don't want to poke at Swagger.

**Auth:** `POST /auth/login` returns a bearer token. Send it as
`Authorization: Bearer <token>` on every other call. Roles are enforced
server-side; the table below says who may call what.

Roles: `school_operator`, `cb_operator`, `coordinator`, `agronomist`, `admin`.
"any" means any authenticated user.

## Auth

### POST /auth/login — anyone
```json
{"username": "coordinator", "password": "demo1234"}
```
→ `{"token": "…", "user": {…}}`. 401 on bad credentials.

### GET /auth/me — any
Returns the current user object.

## Sites

### GET /sites — any
The multi-site overview. One card per site:
```json
{"id": "…", "name": "GSS Maroua Bottle Farm", "site_type": "school",
 "location": "Maroua", "crop_name": "lettuce", "status": "green",
 "active_alerts": 0, "last_updated": "…", "node_online": true}
```
`status` is the traffic light: `green` (all in band), `amber` (Watch or
Acknowledged open), `red` (Alert Raised / Notification Sent open),
`offline` (node silent past the freshness window).

### GET /sites/{id} — any
Card fields plus the full `crop_profile` (all 14 band values) and the
assigned `operators`.

### POST /sites — admin only
Register a site (business rule: only administrators).
```json
{"name": "…", "site_type": "school|community", "location": "…",
 "crop_name": "lettuce", "connectivity": "wifi|gsm"}
```
Creates the site and its sensor node; the simulator picks it up on the next
tick, so a new site has live data within seconds.

### PATCH /sites/{id}/thresholds — admin, coordinator
Partial update of the site's crop band; any subset of the 14 `*_min`/`*_max`
fields, or `crop_name` to switch crop. Every change is tamper-logged with
old and new values. Note: profiles are shared per crop (see ARCHITECTURE.md).

### GET /crops — any
The four crop profiles with their bands.

## Readings

### GET /readings?site_id=…&hours=24 — any
What the dashboard polls. One entry per parameter:
```json
{"parameter": "ph", "band_min": 5.5, "band_max": 6.5,
 "latest": 6.02, "latest_ts": "…", "in_band": true,
 "points": [{"ts": "…", "value": 6.1}, …]}
```

### GET /readings/export.csv?site_id=…&days=30 — agronomist, coordinator, admin
CSV download (`timestamp_utc,site,parameter,value`). The researcher/export
use case; operators use the charts.

## Alerts

### GET /alerts?site_id=…&active=true&limit=100 — any
Alerts newest-first, each with its current lifecycle state and the
per-state timestamps. `active=true` filters to Watch / Alert Raised /
Notification Sent / Acknowledged.

### POST /alerts/{id}/ack — operator of that site, coordinator, admin
`operatorAcknowledgement`: moves Notification Sent → Acknowledged. 403 if an
operator tries another site's alert (business rule), 409 if the alert isn't
in an acknowledgeable state.

### POST /alerts/{id}/close — coordinator, admin
`closeAlert`: Resolved → Closed. 409 unless the alert is Resolved
(unacknowledged alerts close themselves via the timeout instead).

## Notifications

### GET /notifications?unread_only=true&limit=20 — any
The dashboard banner feed: unread dashboard-channel notifications for the
current user. Coordinators/admins see all sites' banners. Each entry
carries the alert's structured facts (`site_name`, `parameter`,
`trigger_value`, `band_min`, `band_max`) alongside the stored `message`,
so the dashboard renders banners in the viewer's current UI language;
the stored `message` is the fixed-at-send-time record.

### POST /notifications/{id}/read — any
Marks a banner dismissed. 204.

### GET /notifications/outbox?channel=sms&limit=100 — admin only
Every dispatched notification on every channel, including the exact
email/SMS/USSD text that *would* have been sent (`status: "simulated"`).
This is the dev panel data source.

## USSD

### POST /ussd — no auth token; identity = phone number
Emulates an aggregator webhook. The phone number must belong to a
registered operator (business rule: USSD sessions are tied to the SIM).
```json
{"phone": "+237650000002", "text": "3*1"}
```
`text` is the '*'-joined keypress history for the session ("" = just
dialed). → `{"message": "…", "end": false}`; `end: true` terminates the
session. Menu: 1 today's readings, 2 current alerts, 3 acknowledge
(then alert number — three presses total), 4 language, 0 exit. Screens are
clipped to 182 chars.

## Admin

### GET /admin/audit?action=…&site_id=…&limit=200 — admin, coordinator
The append-only audit log, newest first. There is deliberately no write,
update or delete endpoint for audit entries.

### GET /admin/health — any
Node health (FR 8.2): last-seen timestamp and online flag per site.

### GET /admin/users — admin only
All users.

### POST /admin/users — admin only
Create an operator/user: username, password, name, role, optional site
assignment, phone, email, language (`en`/`fr`), preferred channel.

### PATCH /admin/users/{id} — admin only
Update site assignment, contacts, language, channel, or `active`
(deactivation instead of deletion, so audit history keeps its actor names).

## Meta

### GET /api/v1/status — anyone
`{"ok": true, "timescaledb": false}` — liveness plus whether the
TimescaleDB extension was available at startup.

## Error shape

All errors are FastAPI-standard: `{"detail": "human-readable reason"}` with
an appropriate status (401 bad/missing token, 403 wrong role or wrong site,
404 unknown id, 409 illegal state transition, 422 malformed body).
