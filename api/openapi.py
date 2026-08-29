"""Small, dependency-free OpenAPI document for the public Flask API contract."""

from __future__ import annotations

from typing import Any

from triguard.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    HealthResponse,
    MonitoringResponse,
    PredictionResult,
    SupplyChainCase,
)


def _schemas() -> dict[str, Any]:
    models = (
        SupplyChainCase,
        BatchPredictionRequest,
        BatchPredictionResponse,
        PredictionResult,
        HealthResponse,
        MonitoringResponse,
    )
    components: dict[str, Any] = {}
    for model in models:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(schema.pop("$defs", {}))
        components[model.__name__] = schema
    components["Error"] = {
        "type": "object",
        "required": ["error", "request_id", "timestamp"],
        "properties": {
            "error": {"type": "object"},
            "request_id": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
        },
    }
    return components


def build_openapi_spec() -> dict[str, Any]:
    error_response = {
        "description": "Request failed.",
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }
    api_key = [{"ApiKeyAuth": []}]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "TriGuard API",
            "version": "1.0.0",
            "description": "Decision support for essential-medicine supply-chain disruption triage.",
        },
        "paths": {
            "/health": {
                "get": {
                    "summary": "Liveness and model readiness",
                    "responses": {"200": {"description": "Service is ready."}, "503": error_response},
                }
            },
            "/v1/model-card": {
                "get": {
                    "summary": "Approved model metadata and limitations",
                    "security": api_key,
                    "responses": {"200": {"description": "Model card."}, "401": error_response, "503": error_response},
                }
            },
            "/v1/predictions": {
                "post": {
                    "summary": "Score one supply-chain case",
                    "security": api_key,
                    "requestBody": _json_request("SupplyChainCase"),
                    "responses": {"200": _json_response("PredictionResult"), "401": error_response, "415": error_response, "422": error_response, "503": error_response},
                }
            },
            "/v1/predictions/batch": {
                "post": {
                    "summary": "Atomically score a validated batch",
                    "security": api_key,
                    "requestBody": _json_request("BatchPredictionRequest"),
                    "responses": {"200": _json_response("BatchPredictionResponse"), "401": error_response, "413": error_response, "422": error_response, "503": error_response},
                }
            },
            "/v1/monitoring/input-drift": {
                "post": {
                    "summary": "Assess batch input distribution against the training reference",
                    "security": api_key,
                    "requestBody": _json_request("BatchPredictionRequest"),
                    "responses": {"200": _json_response("MonitoringResponse"), "401": error_response, "413": error_response, "422": error_response},
                }
            },
            "/v1/metrics": {
                "get": {"summary": "Prometheus metrics", "security": api_key, "responses": {"200": {"description": "Metrics exposition."}, "401": error_response}}
            },
        },
        "components": {
            "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
            "schemas": _schemas(),
        },
    }


def _json_request(schema_name: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def _json_response(schema_name: str) -> dict[str, Any]:
    return {
        "description": "Successful response.",
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }
