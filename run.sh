#!/usr/bin/env bash
# One-command launcher: checks PostgreSQL, creates the venv on first run,
# applies migrations, then starts the API + dashboard on one port.
set -euo pipefail
cd "$(dirname "$0")"

PG_BIN=""
for candidate in /Applications/Postgres.app/Contents/Versions/latest/bin "$(dirname "$(command -v psql 2>/dev/null || true)")"; do
  if [ -x "$candidate/pg_isready" ]; then PG_BIN="$candidate"; break; fi
done

if [ -n "$PG_BIN" ] && ! "$PG_BIN/pg_isready" -q 2>/dev/null; then
  echo "PostgreSQL is not running. Starting Postgres.app..."
  open -a Postgres 2>/dev/null || { echo "Start your PostgreSQL server, then re-run."; exit 1; }
  sleep 4
fi

if [ -n "$PG_BIN" ]; then
  "$PG_BIN/psql" -h localhost -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='vertibottle'" | grep -q 1 \
    || "$PG_BIN/createdb" -h localhost vertibottle
fi

if [ ! -d .venv ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

(cd backend && ../.venv/bin/alembic upgrade head)

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
echo
echo "VertiBottle → http://$HOST:$PORT   (API docs at /docs)"
echo
cd backend
exec ../.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
