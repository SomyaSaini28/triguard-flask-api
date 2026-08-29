"""Database models and bootstrap helpers for the protected planner workspace."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import generate_password_hash

from .config import Settings


db = SQLAlchemy()


class User(db.Model):  # type: ignore[name-defined]
    """A planner account with access to its own assessment history."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    assessments: Mapped[list["AssessmentRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    email_verification: Mapped["EmailVerification | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class EmailVerification(db.Model):  # type: ignore[name-defined]
    """A one-time, expiring verification token for a planner email address."""

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="email_verification")


class ApplicationState(db.Model):  # type: ignore[name-defined]
    """Small one-time data-migration markers kept inside the application database."""

    __tablename__ = "application_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AssessmentRecord(db.Model):  # type: ignore[name-defined]
    """A saved prediction result that can be reviewed by its authenticated owner."""

    __tablename__ = "assessment_records"
    __table_args__ = (Index("idx_assessment_records_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(80))
    medicine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(20), nullable=False)
    triage_action: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    response_sla: Mapped[str] = mapped_column(String(80), nullable=False)
    result_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    user: Mapped[User] = relationship(back_populates="assessments")


def initialize_database(app: Flask, app_settings: Settings) -> None:
    """Create the local schema and optionally bootstrap the first administrator."""
    if app_settings.database_url.startswith("sqlite:///") and app_settings.database_url != "sqlite:///:memory:":
        database_file = Path(app_settings.database_url.removeprefix("sqlite:///"))
        database_file.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        _mark_legacy_accounts_verified()
        _bootstrap_administrator(app_settings)
        if app_settings.environment == "production" and not app.testing and not db.session.scalar(select(User.id).limit(1)):
            raise RuntimeError(
                "TRIGUARD_ADMIN_EMAIL and TRIGUARD_ADMIN_PASSWORD must be set for a new production database."
            )


def _bootstrap_administrator(app_settings: Settings) -> None:
    """Create one initial account from deployment secrets, never from source code."""
    if not app_settings.admin_email or not app_settings.admin_password:
        return

    email = app_settings.admin_email.strip().lower()
    if not email:
        return

    existing_user = db.session.scalar(select(User).where(User.email == email))
    if existing_user:
        # This keeps local setup repeatable for first-time developers. Production
        # passwords are intentionally never changed by an environment restart.
        if app_settings.environment == "development":
            existing_user.password_hash = generate_password_hash(app_settings.admin_password)
            db.session.commit()
        _mark_email_verified(existing_user)
        return

    user = User(email=email, password_hash=generate_password_hash(app_settings.admin_password))
    db.session.add(user)
    db.session.commit()
    _mark_email_verified(user)


def _mark_legacy_accounts_verified() -> None:
    """Preserve access for accounts created before email verification was introduced."""
    migration_key = "email-verification-v1"
    if db.session.get(ApplicationState, migration_key):
        return

    verified_at = datetime.now(UTC)
    for user in db.session.scalars(select(User)).all():
        if user.email_verification is None:
            db.session.add(EmailVerification(user=user, verified_at=verified_at))
    db.session.add(ApplicationState(key=migration_key, value="completed"))
    db.session.commit()


def _mark_email_verified(user: User) -> None:
    verification = user.email_verification or EmailVerification(user=user)
    verification.token_hash = None
    verification.expires_at = None
    verification.verified_at = datetime.now(UTC)
    db.session.add(verification)
    db.session.commit()


def is_email_verified(user: User) -> bool:
    return bool(user.email_verification and user.email_verification.verified_at)


def issue_verification_token(user: User, ttl_minutes: int) -> str:
    """Create or rotate an expiring verification token and store only its hash."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    verification = user.email_verification or EmailVerification(user=user)
    verification.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verification.expires_at = now + timedelta(minutes=ttl_minutes)
    verification.last_sent_at = now
    verification.verified_at = None
    db.session.add(verification)
    db.session.commit()
    return token


def verification_was_sent_recently(user: User, cooldown_minutes: int = 1) -> bool:
    """Return whether a fresh verification message would exceed the send cooldown."""
    verification = user.email_verification
    if verification is None or verification.last_sent_at is None:
        return False
    return datetime.now(UTC) - _as_utc(verification.last_sent_at) < timedelta(minutes=cooldown_minutes)


def confirm_verification_token(token: str) -> User | None:
    """Mark the associated account verified if an unexpired token matches."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verification = db.session.scalar(select(EmailVerification).where(EmailVerification.token_hash == token_hash))
    now = datetime.now(UTC)
    expires_at = _as_utc(verification.expires_at) if verification and verification.expires_at else None
    if verification is None or expires_at is None or expires_at < now:
        return None

    verification.token_hash = None
    verification.expires_at = None
    verification.verified_at = now
    db.session.commit()
    return verification.user


def _as_utc(value: datetime) -> datetime:
    """Normalise SQLite's timezone-naive datetimes before comparing with UTC timestamps."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
