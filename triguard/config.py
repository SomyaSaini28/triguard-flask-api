"""Centralised, environment-aware application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _csv_setting(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())


def _normalise_database_url(database_url: str) -> str:
    """Use psycopg for provider PostgreSQL URLs while leaving SQLite unchanged."""
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


def _database_url() -> str:
    local_default = f"sqlite:///{(PROJECT_ROOT / 'outputs/database/triguard.db').as_posix()}"
    return _normalise_database_url(os.getenv("TRIGUARD_DATABASE_URL", local_default))


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Environment variables override safe local defaults."""

    model_path: Path = Path(os.getenv(
        "TRIGUARD_MODEL_PATH", PROJECT_ROOT / "outputs/models/triguard_model_v3.pkl"
    ))
    metadata_path: Path = Path(os.getenv(
        "TRIGUARD_METADATA_PATH", PROJECT_ROOT / "outputs/models/triguard_model_v3_metadata.json"
    ))
    baseline_data_path: Path = Path(os.getenv(
        "TRIGUARD_BASELINE_DATA", PROJECT_ROOT / "data/processed/supply_chain_cases.csv"
    ))
    audit_log_path: Path = Path(os.getenv(
        "TRIGUARD_AUDIT_LOG", PROJECT_ROOT / "outputs/audit/prediction_events.jsonl"
    ))
    database_url: str = _database_url()
    session_secret: str | None = os.getenv("TRIGUARD_SESSION_SECRET") or None
    admin_email: str | None = os.getenv("TRIGUARD_ADMIN_EMAIL") or None
    admin_password: str | None = os.getenv("TRIGUARD_ADMIN_PASSWORD") or None
    allow_self_signup: bool = os.getenv(
        "TRIGUARD_ALLOW_SELF_SIGNUP", "false"
    ).strip().lower() in {"1", "true", "yes"}
    public_base_url: str = os.getenv("TRIGUARD_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    email_delivery_mode: str = os.getenv("TRIGUARD_EMAIL_DELIVERY", "console").lower()
    email_from: str = os.getenv("TRIGUARD_EMAIL_FROM", "no-reply@triguard.local")
    smtp_host: str | None = os.getenv("TRIGUARD_SMTP_HOST") or None
    smtp_port: int = int(os.getenv("TRIGUARD_SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("TRIGUARD_SMTP_USERNAME") or None
    smtp_password: str | None = os.getenv("TRIGUARD_SMTP_PASSWORD") or None
    smtp_starttls: bool = os.getenv("TRIGUARD_SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes"}
    verification_ttl_minutes: int = int(os.getenv("TRIGUARD_VERIFICATION_TTL_MINUTES", "1440"))
    environment: str = os.getenv("TRIGUARD_ENV", "production").lower()
    api_key: str | None = os.getenv("TRIGUARD_API_KEY") or None
    allowed_origins: tuple[str, ...] = _csv_setting("TRIGUARD_ALLOWED_ORIGINS")
    max_batch_size: int = int(os.getenv("TRIGUARD_MAX_BATCH_SIZE", "500"))
    max_request_bytes: int = int(os.getenv("TRIGUARD_MAX_REQUEST_BYTES", str(1 * 1024 * 1024)))
    trusted_hosts: tuple[str, ...] = _csv_setting("TRIGUARD_TRUSTED_HOSTS")
    proxy_fix_x_for: int = int(os.getenv("TRIGUARD_PROXY_FIX_X_FOR", "0"))
    proxy_fix_x_proto: int = int(os.getenv("TRIGUARD_PROXY_FIX_X_PROTO", "0"))
    proxy_fix_x_host: int = int(os.getenv("TRIGUARD_PROXY_FIX_X_HOST", "0"))
    log_level: str = os.getenv("TRIGUARD_LOG_LEVEL", "INFO")


settings = Settings()
