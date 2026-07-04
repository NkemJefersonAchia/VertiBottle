"""Application configuration.

Every setting can be overridden with an environment variable of the same
name (or via a .env file in the project root). See docs/CONFIG.md for the
full reference.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL connection. Postgres.app default: current macOS user, no password.
    # pg8000 needs the username spelled out, so we resolve it at import time.
    DATABASE_URL: str = ""

    def resolved_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        import getpass

        return f"postgresql+pg8000://{getpass.getuser()}@localhost:5432/vertibottle"

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

    # Bind address for uvicorn (used by run.sh).
    HOST: str = "127.0.0.1"
    PORT: int = 8000


settings = Settings()
