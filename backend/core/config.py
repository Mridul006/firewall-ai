"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central application settings loaded once at import time."""

    APP_ENV: str = os.getenv("APP_ENV", "development")

    POSTGRES_URL: str = os.getenv("POSTGRES_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    CLICKHOUSE_HOST: str = os.getenv("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT: int = int(os.getenv("CLICKHOUSE_PORT", "9000"))

    # anomaly_score above which a traffic event counts as alert-worthy — distinct
    # from ANOMALY_CONTAMINATION (ml/'s IsolationForest training hyperparameter,
    # an expected-fraction, not a score cutoff). Matches the 0.5 convention
    # already used by ml/anomaly.py's detect_anomalies() and
    # sandbox/fp_scorer.py's ANOMALY_SCORE_THRESHOLD.
    ANOMALY_ALERT_THRESHOLD: float = float(os.getenv("ANOMALY_ALERT_THRESHOLD", "0.5"))

    def __init__(self) -> None:
        if not self.POSTGRES_URL:
            raise RuntimeError("POSTGRES_URL is not set — check .env")
        if not self.JWT_SECRET_KEY:
            raise RuntimeError("JWT_SECRET_KEY is not set — check .env")

    @property
    def ASYNC_POSTGRES_URL(self) -> str:
        """POSTGRES_URL rewritten to use the async psycopg driver."""
        return self.POSTGRES_URL.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()
