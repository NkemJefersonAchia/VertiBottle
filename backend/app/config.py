"""Application configuration.

Every setting can be overridden with an environment variable of the same
name (or via a .env file in the project root). See docs/CONFIG.md for the
full reference.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL connection.
    #  - Local dev (empty): Postgres.app default — current macOS user, no
    #    password, pg8000 driver (pure Python, works on the dev machine's
    #    Python 3.14 where psycopg has no wheels).
    #  - Production (set by the host, e.g. Render): a bare
    #    "postgresql://user:pass@host/db" URL. We normalise it below to pick
    #    an installed driver (psycopg on Linux, pg8000 as fallback) and to
    #    require TLS for any non-local host.
    DATABASE_URL: str = ""

    @staticmethod
    def _driver() -> str:
        try:
            import psycopg  # noqa: F401
            return "psycopg"
        except Exception:
            return "pg8000"

    def resolved_database_url(self) -> str:
        raw = self.DATABASE_URL
        if not raw:
            import getpass
            return f"postgresql+pg8000://{getpass.getuser()}@localhost:5432/vertibottle"

        scheme, sep, rest = raw.partition("://")
        if not sep:
            return raw  # not a URL we recognise; hand it through untouched
        # Add a driver if the host gave us a bare postgres/postgresql scheme.
        if "+" not in scheme:
            driver = self._driver()
            raw = f"postgresql+{driver}://{rest}"
            scheme = f"postgresql+{driver}"
        # Managed Postgres requires TLS; psycopg reads sslmode from the URL.
        is_local = "@localhost" in raw or "@127.0.0.1" in raw
        if "psycopg" in scheme and "sslmode=" not in raw and not is_local:
            raw += ("&" if "?" in raw else "?") + "sslmode=require"
        return raw

    # Simulator cadence. Real hardware samples air params every 5 min and
    # water quality every 15 min (FR 1.2); we compress that to a few seconds
    # so the demo dashboard is visibly alive.
    SIM_INTERVAL_SECONDS: float = 10.0

    # Probability per tick that a healthy site/parameter starts drifting out
    # of its crop band. Tuned so an alert fires within the first couple of
    # minutes of a demo without the whole board turning red.
    SIM_DRIFT_PROBABILITY: float = 0.005

    # How many ticks a drift episode lasts before the value recovers.
    SIM_DRIFT_DURATION_TICKS: int = 6

    # Alerts in Notification Sent that receive no acknowledgement within this
    # window take the timeoutExpired shortcut straight to Closed (SRS state
    # machine, Appendix B diagram 4).
    ALERT_ACK_TIMEOUT_SECONDS: int = 600

    # A node silent for longer than this is shown as offline (NFR 2.2 says
    # 60 minutes for real hardware; scaled down so it is demoable).
    NODE_OFFLINE_AFTER_SECONDS: int = 120

    # SRS business rule: max notification dispatches per channel per site per day.
    NOTIFICATION_DAILY_LIMIT: int = 20

    # Retention window for raw readings and their per-reading audit rows. The
    # simulator periodically prunes anything older, so the readings table stays
    # small and dashboard/chart queries stay fast on a long-running deploy.
    # Set to 0 to disable pruning (keep everything). Charts request up to 24h.
    RETENTION_HOURS: int = 48

    # Bind address for uvicorn (used by run.sh).
    HOST: str = "127.0.0.1"
    PORT: int = 8000


settings = Settings()
