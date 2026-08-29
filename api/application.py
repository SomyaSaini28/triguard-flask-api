"""Flask application factory and cross-cutting HTTP concerns."""

from __future__ import annotations

import logging
import json
import re
import time
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from flask import Flask, Response, current_app, g, jsonify, request
from flask_cors import CORS
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from triguard.config import Settings, settings
from triguard.persistence import initialize_database
from triguard.security import csrf_token
from triguard.service import ModelService


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class APIError(Exception):
    """A client-safe error raised by the HTTP boundary."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def current_settings() -> Settings:
    """Return the immutable settings object bound to the current Flask app."""
    return current_app.config["TRIGUARD_SETTINGS"]


def get_service() -> ModelService:
    """Return the process-local service instance created by the app factory."""
    return current_app.extensions["triguard_model_service"]


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    """Build a configured Flask WSGI application.

    The factory keeps test instances isolated and lets a deployment inject an immutable
    settings object without mutating module-level state.
    """
    application_settings = test_config.get("TRIGUARD_SETTINGS", settings) if test_config else settings
    if not isinstance(application_settings, Settings):
        raise TypeError("TRIGUARD_SETTINGS must be an instance of triguard.config.Settings")

    is_test = bool(test_config and test_config.get("TESTING"))
    session_secret = application_settings.session_secret
    if not session_secret:
        if application_settings.environment == "production" and not is_test:
            raise RuntimeError("TRIGUARD_SESSION_SECRET must be set when TRIGUARD_ENV is production.")
        session_secret = token_urlsafe(48)
    if application_settings.environment == "production" and application_settings.allow_self_signup and not is_test:
        if (
            application_settings.email_delivery_mode != "smtp"
            or not application_settings.smtp_host
            or not application_settings.public_base_url.startswith("https://")
        ):
            raise RuntimeError(
                "Production self-signup requires SMTP email delivery and an HTTPS TRIGUARD_PUBLIC_BASE_URL."
            )

    app = Flask(__name__)
    app.config.from_mapping(
        ENV=application_settings.environment,
        MAX_CONTENT_LENGTH=application_settings.max_request_bytes,
        PROPAGATE_EXCEPTIONS=False,
        SECRET_KEY=session_secret,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=application_settings.environment == "production",
        SQLALCHEMY_DATABASE_URI=application_settings.database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TRIGUARD_SETTINGS=application_settings,
        TRUSTED_HOSTS=list(application_settings.trusted_hosts) or None,
    )
    if test_config:
        app.config.update(test_config)

    app.jinja_env.globals["csrf_token"] = csrf_token

    if any((
        application_settings.proxy_fix_x_for,
        application_settings.proxy_fix_x_proto,
        application_settings.proxy_fix_x_host,
    )):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=application_settings.proxy_fix_x_for,
            x_proto=application_settings.proxy_fix_x_proto,
            x_host=application_settings.proxy_fix_x_host,
        )

    initialize_database(app, application_settings)
    app.extensions["triguard_model_service"] = ModelService(application_settings)
    _configure_logging(app, application_settings.log_level)
    _configure_metrics(app)
    _configure_cors(app, application_settings)
    _register_request_lifecycle(app)
    _register_error_handlers(app)

    from api.routes import api

    app.register_blueprint(api)
    return app


def _configure_logging(app: Flask, level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    app.logger.setLevel(level)


def _configure_metrics(app: Flask) -> None:
    registry = CollectorRegistry()
    app.extensions["triguard_metrics"] = {
        "registry": registry,
        "requests": Counter(
            "triguard_http_requests_total",
            "HTTP responses served by TriGuard.",
            ("method", "endpoint", "status"),
            registry=registry,
        ),
        "latency": Histogram(
            "triguard_http_request_duration_seconds",
            "TriGuard HTTP request duration in seconds.",
            ("method", "endpoint"),
            registry=registry,
        ),
    }


def _configure_cors(app: Flask, application_settings: Settings) -> None:
    """Enable browser access only for explicitly allowlisted origins."""
    if not application_settings.allowed_origins:
        return
    CORS(
        app,
        resources={r"/v1/*": {"origins": list(application_settings.allowed_origins)}},
        methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "X-Client-Source"],
        expose_headers=["X-Request-ID"],
        supports_credentials=False,
        max_age=600,
    )


def _register_request_lifecycle(app: Flask) -> None:
    @app.before_request
    def establish_request_context() -> None:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        g.request_id = supplied_request_id if REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
        g.request_started_at = time.perf_counter()

    @app.after_request
    def add_response_headers_and_observability(response: Response) -> Response:
        response.headers["X-Request-ID"] = getattr(g, "request_id", str(uuid4()))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.endpoint in {
            "api.index", "api.login", "api.signup", "api.resend_verification", "api.verify_email", "api.assessment_history"
        }:
            # Browser pages serve their assets from this application. Keep their
            # policy self-contained while retaining the stricter no-content policy for APIs.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        started_at = getattr(g, "request_started_at", None)
        if started_at is not None:
            duration = time.perf_counter() - started_at
            endpoint = request.endpoint or "unmatched"
            metrics = app.extensions["triguard_metrics"]
            metrics["requests"].labels(request.method, endpoint, str(response.status_code)).inc()
            metrics["latency"].labels(request.method, endpoint).observe(duration)
            app.logger.info(
                "request_completed request_id=%s method=%s endpoint=%s status=%s duration_ms=%.1f",
                g.request_id,
                request.method,
                endpoint,
                response.status_code,
                duration * 1000,
            )
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError) -> tuple[Response, int]:
        return _error_response(error.status_code, error.code, error.message, error.details)

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[Response, int]:
        return _error_response(
            422,
            "validation_error",
            "Request validation failed.",
            json.loads(error.json(include_url=False)),
        )

    @app.errorhandler(FileNotFoundError)
    def handle_missing_artifact(_: FileNotFoundError) -> tuple[Response, int]:
        app.logger.warning("model_artifact_unavailable request_id=%s", getattr(g, "request_id", "unknown"))
        return _error_response(503, "model_unavailable", "Model artifact is unavailable.")

    @app.errorhandler(ValueError)
    def handle_invalid_artifact(_: ValueError) -> tuple[Response, int]:
        app.logger.warning("invalid_model_artifact request_id=%s", getattr(g, "request_id", "unknown"))
        return _error_response(503, "model_unavailable", "Model artifact failed integrity checks.")

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_request(_: RequestEntityTooLarge) -> tuple[Response, int]:
        return _error_response(413, "request_too_large", "Request body exceeds the configured size limit.")

    @app.errorhandler(BadRequest)
    def handle_malformed_json(_: BadRequest) -> tuple[Response, int]:
        return _error_response(400, "invalid_json", "Request body must contain valid JSON.")

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        code = "not_found" if error.code == 404 else "method_not_allowed" if error.code == 405 else "bad_request"
        message = "The requested resource was not found." if error.code == 404 else error.description
        return _error_response(error.code or 500, code, message)

    @app.errorhandler(Exception)
    def handle_unexpected_error(_: Exception) -> tuple[Response, int]:
        app.logger.exception("unhandled_exception request_id=%s", getattr(g, "request_id", "unknown"))
        return _error_response(500, "internal_error", "An unexpected server error occurred.")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> tuple[Response, int]:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return jsonify({
        "error": error,
        "request_id": getattr(g, "request_id", None),
        "timestamp": datetime.now(UTC).isoformat(),
    }), status_code


def metrics_response() -> Response:
    """Render the app-local Prometheus registry."""
    registry = current_app.extensions["triguard_metrics"]["registry"]
    return Response(generate_latest(registry), mimetype="text/plain; version=0.0.4; charset=utf-8")
