import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from api.application import create_app
from triguard.config import Settings, _normalise_database_url, settings


def payload() -> dict:
    return {
        "case_id": "API-001", "medicine_name": "Insulin", "medicine_criticality": 5,
        "cold_chain_required": True, "supplier_id": "S2", "destination_facility": "District Hospital Jaipur",
        "supplier_on_time_rate": 0.68, "supplier_fill_rate": 0.72, "lead_time_days": 8,
        "lead_time_variability": 4.5, "route_delay_days": 3.8, "weather_risk_score": 8,
        "demand_spike_factor": 1.4, "current_stock_days": 3, "warehouse_utilization": 88,
    }


@pytest.fixture
def client(tmp_path: Path):
    local_settings = Settings(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
        database_url=f"sqlite:///{(tmp_path / 'triguard.db').as_posix()}",
        session_secret="test-session-secret",
        admin_email="planner@example.com",
        admin_password="test-password",
        allow_self_signup=True,
    )
    app = create_app({"TESTING": True, "TRIGUARD_SETTINGS": local_settings})
    return app.test_client()


def login(client):
    client.get("/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["csrf_token"]
    return client.post(
        "/login",
        data={"email": "planner@example.com", "password": "test-password", "_csrf_token": csrf_token},
        follow_redirects=False,
    )


def test_health_reports_model_readiness(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json["model_loaded"] is True
    assert response.headers["X-Request-ID"]


def test_hosted_postgres_urls_use_the_installed_psycopg_driver():
    assert _normalise_database_url("postgresql://user:password@db.example/database") == (
        "postgresql+psycopg://user:password@db.example/database"
    )


def test_dashboard_homepage_is_served(client):
    assert client.get("/").status_code == 302
    assert login(client).status_code == 302
    response = client.get("/")

    assert response.status_code == 200
    assert b"Supply continuity command center" in response.data
    assert b"dashboard.css" in response.data
    assert "style-src 'self'" in response.headers["Content-Security-Policy"]


def test_login_page_can_load_its_same_origin_styles(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Sign in to continue" in response.data
    assert "style-src 'self'" in response.headers["Content-Security-Policy"]


def test_signup_requires_email_verification_before_workspace_access(client):
    client.get("/signup")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["csrf_token"]
    response = client.post(
        "/signup",
        data={
            "email": "new.planner@example.com",
            "password": "planner-password-123",
            "confirm_password": "planner-password-123",
            "_csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert b"Verify your email" in response.data
    assert b"Local development link" in response.data
    assert client.get("/").status_code == 302

    client.get("/login")
    with client.session_transaction() as browser_session:
        login_csrf_token = browser_session["csrf_token"]
    unverified_login = client.post(
        "/login",
        data={
            "email": "new.planner@example.com",
            "password": "planner-password-123",
            "_csrf_token": login_csrf_token,
        },
    )
    assert b"Verify your email before signing in" in unverified_login.data

    match = re.search(rb'href="(http://127\.0\.0\.1:8000/verify-email\?token=[^"]+)"', response.data)
    assert match is not None
    verification_url = match.group(1).decode("utf-8")
    verification_path = urlsplit(verification_url).path + "?" + urlsplit(verification_url).query
    verified = client.get(verification_path)
    assert verified.status_code == 200
    assert b"Your account is ready" in verified.data
    assert client.get("/").status_code == 200
    assert client.get(verification_path).status_code == 400

    duplicate_client = client.application.test_client()
    duplicate_client.get("/signup")
    with duplicate_client.session_transaction() as browser_session:
        duplicate_csrf_token = browser_session["csrf_token"]
    duplicate = duplicate_client.post(
        "/signup",
        data={
            "email": "new.planner@example.com",
            "password": "planner-password-123",
            "confirm_password": "planner-password-123",
            "_csrf_token": duplicate_csrf_token,
        },
    )
    assert b"already exists" in duplicate.data


def test_production_self_signup_requires_smtp_and_https_url(tmp_path: Path):
    production_settings = Settings(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
        database_url=f"sqlite:///{(tmp_path / 'triguard.db').as_posix()}",
        environment="production",
        session_secret="test-session-secret",
        admin_email="planner@example.com",
        admin_password="test-password",
        allow_self_signup=True,
    )

    with pytest.raises(RuntimeError, match="SMTP email delivery"):
        create_app({"TRIGUARD_SETTINGS": production_settings})


def test_dashboard_prediction_is_saved_to_authenticated_history(client):
    assert login(client).status_code == 302
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["csrf_token"]

    response = client.post("/dashboard/predictions", json=payload(), headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert response.json["case_id"] == "API-001"
    history = client.get("/history")
    assert history.status_code == 200
    assert b"API-001" in history.data


def test_score_endpoint_returns_a_decision_brief(client):
    response = client.post("/v1/predictions", json=payload(), headers={"X-Request-ID": "test-request-1"})

    assert response.status_code == 200
    assert response.json["model_version"] == "v3"
    assert "recommended_actions" in response.json
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"] == "test-request-1"


def test_versioned_endpoints_require_configured_api_key(tmp_path: Path):
    secured_settings = Settings(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
        database_url=f"sqlite:///{(tmp_path / 'triguard.db').as_posix()}",
        session_secret="test-session-secret",
        api_key="test-api-key",
    )
    client = create_app({"TESTING": True, "TRIGUARD_SETTINGS": secured_settings}).test_client()

    assert client.post("/v1/predictions", json=payload()).status_code == 401
    assert client.post("/v1/predictions", json=payload(), headers={"X-API-Key": "test-api-key"}).status_code == 200


def test_new_production_database_requires_an_administrator(tmp_path: Path):
    production_settings = Settings(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
        database_url=f"sqlite:///{(tmp_path / 'triguard.db').as_posix()}",
        environment="production",
        session_secret="test-session-secret",
    )

    with pytest.raises(RuntimeError, match="TRIGUARD_ADMIN_EMAIL"):
        create_app({"TRIGUARD_SETTINGS": production_settings})


def test_development_bootstrap_refreshes_the_local_admin_password(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'triguard.db').as_posix()}"
    base_settings = dict(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
        database_url=database_url,
        environment="development",
        session_secret="test-session-secret",
        admin_email="planner@example.com",
    )
    create_app({"TESTING": True, "TRIGUARD_SETTINGS": Settings(**base_settings, admin_password="first-password")})
    refreshed_client = create_app(
        {"TESTING": True, "TRIGUARD_SETTINGS": Settings(**base_settings, admin_password="second-password")}
    ).test_client()

    refreshed_client.get("/login")
    with refreshed_client.session_transaction() as browser_session:
        csrf_token = browser_session["csrf_token"]
    response = refreshed_client.post(
        "/login",
        data={"email": "planner@example.com", "password": "second-password", "_csrf_token": csrf_token},
    )

    assert response.status_code == 302


def test_invalid_payload_has_a_machine_readable_error(client):
    invalid_payload = payload()
    invalid_payload["unknown_field"] = "not allowed"

    response = client.post("/v1/predictions", json=invalid_payload)

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_error"
    assert response.json["request_id"]


def test_validator_error_with_context_is_still_json_serializable(client):
    invalid_payload = payload()
    invalid_payload["medicine_name"] = " "

    response = client.post("/v1/predictions", json=invalid_payload)

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_error"


def test_malformed_json_has_a_consistent_error(client):
    response = client.post("/v1/predictions", data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_json"


def test_openapi_contract_is_available(client):
    response = client.get("/v1/openapi.json")

    assert response.status_code == 200
    assert response.json["openapi"] == "3.1.0"
    assert "/v1/predictions" in response.json["paths"]
