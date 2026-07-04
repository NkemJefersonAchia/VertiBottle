# Configuration reference

All settings live in `backend/app/config.py` and can be overridden by
environment variables of the same name, or by a `.env` file in the
directory you launch from (`backend/` when using run.sh). Defaults are
chosen so that `./run.sh` works with zero configuration on a fresh
Postgres.app install.

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | *(empty → auto)* | SQLAlchemy connection URL. When empty, resolves to `postgresql+pg8000://<your-macos-user>@localhost:5432/vertibottle`, which matches Postgres.app's trust setup. Set explicitly for Homebrew/remote Postgres, e.g. `postgresql+pg8000://user:pass@host:5432/vertibottle`. |
| `SIM_INTERVAL_SECONDS` | `10.0` | Seconds between simulator ticks. Real hardware samples every 5–30 min (FR 1.2); the compressed default keeps a demo visibly alive. Raise it to reduce data volume. |
| `SIM_DRIFT_PROBABILITY` | `0.005` | Per tick, per (site, parameter) chance that a drift episode starts. 0.005 ≈ one new excursion somewhere every ~5–6 ticks across 35 channels: enough for a demo alert within a couple of minutes without the whole board turning red. Set to `0` for a perfectly calm board, `0.02` for a stress demo. |
| `SIM_DRIFT_DURATION_TICKS` | `6` | How many ticks a drift episode lasts before the value recovers. At the default interval that's ~1 minute out of band — long enough to walk through Watch → Alert → acknowledge → Resolved. |
| `ALERT_ACK_TIMEOUT_SECONDS` | `600` | Alerts sitting in Notification Sent longer than this take the `timeoutExpired` shortcut to Closed. 10 minutes is demo-friendly; the SRS envisions an operator-configured window in production. |
| `NODE_OFFLINE_AFTER_SECONDS` | `120` | A node silent this long shows as offline (grey card, FR 8.2/NFR 2.2). The SRS says 60 min for real 15-min-cadence hardware; scaled to the compressed simulator cadence. Stop the backend and the cards go grey — that's this. |
| `NOTIFICATION_DAILY_LIMIT` | `20` | Max dispatches per channel per site per rolling 24 h (SRS business rule, protects SMS/USSD spend). Hitting the cap is itself audit-logged. |
| `HOST` | `127.0.0.1` | Bind address (used by run.sh). Use `0.0.0.0` to demo to other devices on your network. |
| `PORT` | `8000` | HTTP port (used by run.sh). |

Example — calm simulation, fast timeout, alternative port:

```bash
SIM_DRIFT_PROBABILITY=0.002 ALERT_ACK_TIMEOUT_SECONDS=180 PORT=8010 ./run.sh
```

Frontend knobs (constants in `frontend/app.js`, not env vars, since it's a
static file): `POLL_MS = 30000` — the dashboard poll interval from the SRS.
