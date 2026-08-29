# TriGuard API

TriGuard is a production-oriented Flask API for essential-medicine supply-chain disruption triage. It validates a supply-chain case, estimates calibrated disruption risk, and returns a documented planner action and response SLA.

It is decision support only: the bundled V3 model was trained on synthetic prototype data and must not be used for autonomous clinical, procurement, or emergency-response decisions.

## Highlights

- Flask application factory with versioned JSON endpoints
- Strict Pydantic contracts that reject malformed or unapproved input
- Calibrated model scoring, transparent triage policy, and plain-language operating signals
- API-key enforcement, request correlation IDs, secure default headers, allowlisted CORS, payload limits, and trusted-proxy support
- Privacy-conscious append-only audit events; raw case data is not recorded and case IDs are hashed
- OpenAPI 3.1 contract, Prometheus metrics, readiness endpoint, container health check, and Gunicorn deployment
- Batch input-distribution monitoring, with clear separation from outcome-based performance monitoring

## Quick start

Use Python 3.12 to match the container runtime and install the packaged binary dependencies reliably.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:TRIGUARD_ENV = "development"
$env:TRIGUARD_API_KEY = "local-development-key"
$env:TRIGUARD_SESSION_SECRET = "local-development-session-secret-change-before-hosting"
$env:TRIGUARD_ADMIN_EMAIL = "planner@example.com"
$env:TRIGUARD_ADMIN_PASSWORD = "local-password-change-before-hosting"
$env:TRIGUARD_ALLOW_SELF_SIGNUP = "true"
$env:TRIGUARD_EMAIL_DELIVERY = "console"
$env:TRIGUARD_PUBLIC_BASE_URL = "http://127.0.0.1:8000"
flask --app api.main:app run --port 8000 --debug
```

Open `http://localhost:8000` and sign in with the administrator email and password above. Self-created accounts must verify their email first; in local `console` mode the confirmation page displays the temporary verification link instead of sending a real email. The dashboard stores each signed-in planner's assessments in a local SQLite database at `outputs/database/triguard.db`. Machine-readable API documentation is available at `GET /v1/openapi.json`.

## Example request

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "X-API-Key" = "local-development-key"
  "X-Request-ID" = "demo-001"
}

$body = @{
  case_id = "JAIPUR-2408"
  medicine_name = "Insulin"
  medicine_criticality = 5
  cold_chain_required = $true
  supplier_id = "S2"
  destination_facility = "District Hospital Jaipur"
  supplier_on_time_rate = 0.68
  supplier_fill_rate = 0.72
  lead_time_days = 8
  lead_time_variability = 4.5
  route_delay_days = 3.8
  weather_risk_score = 8
  demand_spike_factor = 1.4
  current_stock_days = 3
  warehouse_utilization = 88
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/predictions -Headers $headers -Body $body
```

Every response includes an `X-Request-ID` header. Reuse an ID supplied by an upstream system to correlate its logs with TriGuard’s audit event.

## Endpoints

| Endpoint | Authentication | Purpose |
|---|---|---|
| `GET /health` | None | Liveness, readiness, and model availability for infrastructure checks. |
| `GET /v1/openapi.json` | None | OpenAPI 3.1 service contract. |
| `GET /v1/model-card` | API key when configured | Approved artifact metadata, metrics, intended use, and limitations. |
| `POST /v1/predictions` | API key when configured | Validate and score one case. |
| `POST /v1/predictions/batch` | API key when configured | Atomically validate and score up to the configured batch limit. |
| `POST /v1/monitoring/input-drift` | API key when configured | Compare a validated batch with the training reference. |
| `GET /v1/metrics` | API key when configured | Prometheus metrics exposition. |

Errors use a stable JSON envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  },
  "request_id": "demo-001",
  "timestamp": "2026-08-26T00:00:00+00:00"
}
```

## Configuration

Copy `.env.example` to `.env` for Docker, or set the values through your deployment’s secret/configuration manager.

| Variable | Purpose |
|---|---|
| `TRIGUARD_API_KEY` | API key required for versioned business endpoints. Never commit a real value. |
| `TRIGUARD_SESSION_SECRET` | Long, random secret used to sign browser sessions. Required in production. |
| `TRIGUARD_ADMIN_EMAIL`, `TRIGUARD_ADMIN_PASSWORD` | Creates the first dashboard user when a new database is initialized. Use deployment secrets, never source code. |
| `TRIGUARD_ALLOW_SELF_SIGNUP` | Enables self-service sign-up. In production, it requires SMTP delivery and an HTTPS public base URL. |
| `TRIGUARD_PUBLIC_BASE_URL` | Public HTTPS URL used inside verification emails; use `http://127.0.0.1:8000` only in local development. |
| `TRIGUARD_EMAIL_DELIVERY` | `console` shows a temporary link locally; `smtp` sends actual verification emails. |
| `TRIGUARD_EMAIL_FROM`, `TRIGUARD_SMTP_HOST`, `TRIGUARD_SMTP_PORT`, `TRIGUARD_SMTP_USERNAME`, `TRIGUARD_SMTP_PASSWORD`, `TRIGUARD_SMTP_STARTTLS` | SMTP provider configuration for public email verification. Keep credentials in the host secret manager. |
| `TRIGUARD_VERIFICATION_TTL_MINUTES` | Lifespan of a verification link; default `1440` (24 hours). |
| `TRIGUARD_DATABASE_URL` | SQLAlchemy URL. Defaults to local SQLite; set a managed PostgreSQL URL for hosting. |
| `TRIGUARD_ALLOWED_ORIGINS` | Comma-separated browser origins. Empty by default for server-to-server use. |
| `TRIGUARD_MAX_BATCH_SIZE` | Maximum cases allowed in one batch; default `500`. |
| `TRIGUARD_MAX_REQUEST_BYTES` | Maximum HTTP request body; default `1048576`. |
| `TRIGUARD_TRUSTED_HOSTS` | Optional comma-separated host allowlist. |
| `TRIGUARD_PROXY_FIX_X_FOR`, `TRIGUARD_PROXY_FIX_X_PROTO`, `TRIGUARD_PROXY_FIX_X_HOST` | Trusted reverse-proxy hops; keep at `0` unless your proxy topology is understood. |
| `TRIGUARD_AUDIT_LOG` | Local audit file location. Use managed, durable logging in a real deployment. |

## Docker deployment

```powershell
Copy-Item .env.example .env
# Set a strong TRIGUARD_API_KEY in .env before starting the service.
docker compose up --build
```

The Compose service binds only to `127.0.0.1:8000`, uses a non-root container user, a read-only filesystem, dropped Linux capabilities, writable audit and database volumes, and a health check. Put it behind a TLS-terminating reverse proxy or ingress gateway to expose it beyond the local host. For a hosted deployment, set `TRIGUARD_DATABASE_URL` to a managed PostgreSQL connection URL and keep all secrets in the host's secret manager.

For a production release, use a secret manager and identity-aware gateway instead of distributing a shared API key; scrape `/v1/metrics` through an authenticated internal network; centralize structured logs and audit events; configure reverse-proxy trust exactly; and apply rate limiting at the gateway.

## Render deployment

The repository includes [`render.yaml`](render.yaml) for a paid Render Web Service, managed PostgreSQL, SMTP email verification, and a Singapore region. Follow [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) after pushing the project to GitHub. The free Render plan is not suitable for this configuration because it blocks outbound SMTP port `587` and its free PostgreSQL database expires after 30 days.

## Decision policy and governance

| Risk probability | Planner response |
|---:|---|
| `< 0.35` | Monitor |
| `0.35–0.59` | Review within one business day |
| `0.60–0.74` | Escalate to planner within four hours |
| `≥ 0.75` with criticality `≥ 4` and stock cover `≤ 5` days | Intervene immediately |

The classification threshold and operational triage policy are intentionally separate. Input-distribution monitoring is an early warning only; verified local outcomes are required to monitor calibration, false negatives, equity, and intervention impact.

Before a real deployment, replace the synthetic training data with governed representative data, perform independent validation, formally approve the intervention policy and named owners, retain audit records in controlled durable storage, and release model changes only through review.

## Development

```powershell
pytest
python src/train_model_v3.py
```

Repository layout:

```text
api/          Flask app factory, versioned routes, and OpenAPI contract
triguard/     Serving, schemas, triage, audit, and monitoring domain logic
src/          Data and model-training workflows
tests/        Domain and HTTP contract tests
outputs/      Versioned model artifacts, evaluations, and local audit events
```

## License

MIT. See [LICENSE](LICENSE).
