"""Versioned Flask routes for TriGuard scoring and governance."""

from __future__ import annotations

import secrets
import re
from functools import wraps
from typing import Any, Callable, TypeVar

from flask import Blueprint, Response, g, jsonify, redirect, render_template, request, session, url_for
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from api.application import APIError, current_settings, get_service, metrics_response
from api.openapi import build_openapi_spec
from triguard.email_delivery import EmailDeliveryError, send_verification_email
from triguard.monitoring import assess_input_drift
from triguard.persistence import (
    AssessmentRecord,
    User,
    confirm_verification_token,
    db,
    is_email_verified,
    issue_verification_token,
    verification_was_sent_recently,
)
from triguard.schemas import BatchPredictionRequest, SupplyChainCase
from triguard.security import csrf_is_valid, csrf_token


api = Blueprint("api", __name__)
F = TypeVar("F", bound=Callable[..., Response | tuple[Response, int]])
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def require_api_key(view: F) -> F:
    """Protect versioned business endpoints when an API key is configured."""
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Response | tuple[Response, int]:
        configured_key = current_settings().api_key
        provided_key = request.headers.get("X-API-Key")
        if configured_key and not (provided_key and secrets.compare_digest(provided_key, configured_key)):
            raise APIError(401, "unauthorized", "A valid X-API-Key header is required.")
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def require_login(view: F) -> F:
    """Require a valid server-side browser session for planner workspace routes."""
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Response | tuple[Response, int]:
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if isinstance(user_id, int) else None
        if user is None:
            session.clear()
            return redirect(url_for("api.login", next=_safe_next_path(request.full_path)))
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def parse_json(model_type: type[BaseModel]) -> BaseModel:
    """Parse JSON once and validate it with the existing strict Pydantic contract."""
    if not request.is_json:
        raise APIError(415, "unsupported_media_type", "Content-Type must be application/json.")
    payload = request.get_json(silent=False)
    if payload is None:
        raise APIError(400, "invalid_json", "Request body must contain a JSON object.")
    return model_type.model_validate(payload)


def client_source(default: str) -> str:
    """Keep optional source labels bounded before they are written to audit logs."""
    return request.headers.get("X-Client-Source", default).strip()[:80] or default


def _safe_next_path(value: str | None) -> str:
    """Accept only local relative redirects to avoid open-redirect login flows."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("api.index")


def _csrf_error() -> APIError:
    return APIError(400, "invalid_csrf_token", "Your session could not be verified. Refresh the page and try again.")


def _start_user_session(user: User) -> None:
    """Rotate session data on authentication to limit fixation risk."""
    session.clear()
    session["user_id"] = user.id
    csrf_token()
    session.permanent = True


def _password_error(password: str, confirmation: str) -> str | None:
    if password != confirmation:
        return "The passwords do not match."
    if len(password) < 12:
        return "Use at least 12 characters for your password."
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        return "Include at least one letter and one number in your password."
    return None


def _send_verification(user: User) -> tuple[str | None, str | None]:
    """Issue a fresh token and send it through the configured mail delivery mode."""
    token = issue_verification_token(user, current_settings().verification_ttl_minutes)
    try:
        development_url = send_verification_email(current_settings(), user.email, token)
    except EmailDeliveryError:
        return (
            "We could not send a verification email. Ask the deployment administrator to check email delivery settings.",
            None,
        )
    return None, development_url


@api.get("/")
@require_login
def index() -> Response:
    """Serve the planner dashboard while keeping the versioned API separate."""
    return render_template("index.html")


@api.route("/login", methods=["GET", "POST"])
def login() -> Response:
    if session.get("user_id"):
        return redirect(_safe_next_path(request.args.get("next")))

    error: str | None = None
    if request.method == "POST":
        if not csrf_is_valid():
            error = "Your session could not be verified. Refresh the page and try again."
        else:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = db.session.scalar(select(User).where(User.email == email))
            if user and check_password_hash(user.password_hash, password):
                if not is_email_verified(user):
                    error = "Verify your email before signing in. You can request a new verification link below."
                    return render_template(
                        "login.html",
                        error=error,
                        signup_enabled=current_settings().allow_self_signup,
                        verification_needed_email=user.email,
                    )
                _start_user_session(user)
                return redirect(_safe_next_path(request.args.get("next")))
            error = "The email or password is incorrect."

    return render_template("login.html", error=error, signup_enabled=current_settings().allow_self_signup)


@api.route("/signup", methods=["GET", "POST"])
def signup() -> Response:
    """Create an unverified planner account when self-service registration is enabled."""
    if session.get("user_id"):
        return redirect(url_for("api.index"))
    if not current_settings().allow_self_signup:
        return redirect(url_for("api.login"))

    error: str | None = None
    if request.method == "POST":
        if not csrf_is_valid():
            error = "Your session could not be verified. Refresh the page and try again."
        else:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            if not EMAIL_PATTERN.fullmatch(email):
                error = "Enter a valid email address."
            else:
                error = _password_error(password, confirmation)

            if error is None:
                user = User(email=email, password_hash=generate_password_hash(password))
                db.session.add(user)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    error = "An account with this email already exists. Sign in instead."
                else:
                    delivery_error, development_verification_url = _send_verification(user)
                    if delivery_error:
                        error = delivery_error
                    else:
                        return render_template(
                            "verification_sent.html",
                            email=user.email,
                            development_verification_url=development_verification_url,
                        )

    return render_template("signup.html", error=error)


@api.post("/resend-verification")
def resend_verification() -> Response:
    if not csrf_is_valid():
        raise _csrf_error()

    email = request.form.get("email", "").strip().lower()
    user = db.session.scalar(select(User).where(User.email == email)) if EMAIL_PATTERN.fullmatch(email) else None
    if user and not is_email_verified(user):
        if not verification_was_sent_recently(user):
            _, development_verification_url = _send_verification(user)
            return render_template(
                "verification_sent.html",
                email=email,
                development_verification_url=development_verification_url,
            )
    return render_template("verification_sent.html", email=email or "your email")


@api.get("/verify-email")
def verify_email() -> Response:
    token = request.args.get("token", "")
    user = confirm_verification_token(token) if token else None
    if user is None:
        return render_template("verification_result.html", verified=False), 400
    _start_user_session(user)
    return render_template("verification_result.html", verified=True, email=user.email)


@api.post("/logout")
def logout() -> Response:
    if not csrf_is_valid():
        raise _csrf_error()
    session.clear()
    return redirect(url_for("api.login"))


@api.post("/dashboard/predictions")
@require_login
def score_dashboard_case() -> Response:
    """Score and persist a planner-owned assessment without exposing an API key."""
    if not csrf_is_valid():
        raise _csrf_error()

    case = parse_json(SupplyChainCase)
    result = get_service().predict(case, source=f"dashboard:user-{g.current_user.id}")
    payload = result.model_dump(mode="json")
    db.session.add(AssessmentRecord(
        id=str(result.request_id),
        user_id=g.current_user.id,
        case_id=result.case_id,
        medicine_name=case.medicine_name,
        risk_probability=result.risk_probability,
        risk_band=result.risk_band,
        triage_action=result.triage_action,
        severity=result.severity,
        response_sla=result.response_sla,
        result_payload=payload,
    ))
    db.session.commit()
    return jsonify(payload)


@api.get("/history")
@require_login
def assessment_history() -> Response:
    records = db.session.scalars(
        select(AssessmentRecord)
        .where(AssessmentRecord.user_id == g.current_user.id)
        .order_by(AssessmentRecord.created_at.desc())
        .limit(100)
    ).all()
    return render_template("history.html", records=records)


@api.get("/health")
def health() -> Response:
    model_loaded, model_version = get_service().health()
    status_code = 200 if model_loaded else 503
    return jsonify({
        "status": "healthy" if model_loaded else "degraded",
        "model_loaded": model_loaded,
        "model_version": model_version,
        "api_key_required": bool(current_settings().api_key),
    }), status_code


@api.get("/v1/openapi.json")
def openapi() -> Response:
    return jsonify(build_openapi_spec())


@api.get("/v1/metrics")
@require_api_key
def metrics() -> Response:
    return metrics_response()


@api.get("/v1/model-card")
@require_api_key
def model_card() -> Response:
    metadata = get_service().metadata
    return jsonify({
        "model_version": metadata["model_version"],
        "model_type": "Calibrated Random Forest",
        "calibration": metadata.get("calibration"),
        "operating_threshold": metadata["operating_threshold"],
        "feature_columns": metadata["feature_columns"],
        "metrics": metadata.get("metrics", {}),
        "intended_use": "Planner decision support for essential-medicine supply-chain disruption triage.",
        "limitations": [
            "The included model was trained and evaluated on synthetic prototype data.",
            "Predictions require human review and must be validated against local operational outcomes before deployment.",
            "Input monitoring detects distribution change, not post-deployment model performance drift.",
        ],
    })


@api.post("/v1/predictions")
@require_api_key
def score_case() -> Response:
    case = parse_json(SupplyChainCase)
    result = get_service().predict(case, source=client_source("api"))
    return jsonify(result.model_dump(mode="json"))


@api.post("/v1/predictions/batch")
@require_api_key
def score_batch() -> Response:
    batch = parse_json(BatchPredictionRequest)
    _assert_batch_size(len(batch.cases))
    source = client_source("api-batch")
    predictions = [get_service().predict(case, source=source) for case in batch.cases]
    summary: dict[str, int] = {}
    for prediction in predictions:
        summary[prediction.triage_action] = summary.get(prediction.triage_action, 0) + 1
    return jsonify({
        "request_id": str(batch.request_id),
        "total_cases": len(predictions),
        "summary": summary,
        "predictions": [prediction.model_dump(mode="json") for prediction in predictions],
    })


@api.post("/v1/monitoring/input-drift")
@require_api_key
def input_drift() -> Response:
    batch = parse_json(BatchPredictionRequest)
    _assert_batch_size(len(batch.cases))
    overall_status, feature_checks = assess_input_drift(
        batch.cases,
        get_service().settings.baseline_data_path,
    )
    return jsonify({
        "assessed_cases": len(batch.cases),
        "overall_status": overall_status,
        "feature_checks": [check.model_dump(mode="json") for check in feature_checks],
    })


def _assert_batch_size(size: int) -> None:
    max_batch_size = current_settings().max_batch_size
    if size > max_batch_size:
        raise APIError(
            413,
            "batch_too_large",
            f"Batch size exceeds the configured limit of {max_batch_size} cases.",
        )
