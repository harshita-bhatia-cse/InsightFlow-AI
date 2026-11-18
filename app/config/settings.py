from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv


production_environment = os.getenv("APP_ENV", "development").strip().lower() == "production"
load_dotenv(override=not production_environment)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_environment: str
    database_url: str
    app_secret_key: str
    quality_alert_threshold: float
    max_upload_size_mb: int
    log_level: str
    access_token_expiry_seconds: int
    token_issuer: str
    token_audience: str
    auto_create_schema: bool
    password_reset_expiry_minutes: int
    auth_rate_limit_requests: int
    auth_rate_limit_window_seconds: int

    @classmethod
    def from_environment(cls) -> "Settings":
        environment = os.getenv("APP_ENV", "development").strip().lower()
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("DATABASE_URL is required.")

        secret_key = os.getenv("APP_SECRET_KEY", "").strip()
        if environment == "production":
            if len(secret_key) < 32:
                raise ValueError(
                    "APP_SECRET_KEY must contain at least 32 characters in production."
                )
        elif not secret_key:
            secret_key = secrets.token_urlsafe(48)

        auto_create_default = environment != "production"
        auto_create_schema = os.getenv(
            "AUTO_CREATE_SCHEMA",
            str(auto_create_default),
        ).strip().lower() in {"1", "true", "yes"}

        auth_rate_limit_default = "100" if environment == "test" else "10"

        return cls(
            app_name=os.getenv("APP_NAME", "InsightFlow").strip(),
            app_environment=environment,
            database_url=database_url,
            app_secret_key=secret_key,
            quality_alert_threshold=float(
                os.getenv("QUALITY_ALERT_THRESHOLD", "70")
            ),
            max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "5")),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            access_token_expiry_seconds=int(
                os.getenv("ACCESS_TOKEN_EXPIRY_SECONDS", "3600")
            ),
            token_issuer=os.getenv("TOKEN_ISSUER", "insightflow-api").strip(),
            token_audience=os.getenv("TOKEN_AUDIENCE", "insightflow-client").strip(),
            auto_create_schema=auto_create_schema,
            password_reset_expiry_minutes=int(
                os.getenv("PASSWORD_RESET_EXPIRY_MINUTES", "30")
            ),
            auth_rate_limit_requests=int(
                os.getenv(
                    "AUTH_RATE_LIMIT_REQUESTS",
                    auth_rate_limit_default,
                )
            ),
            auth_rate_limit_window_seconds=int(
                os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
            ),
        )


settings = Settings.from_environment()
