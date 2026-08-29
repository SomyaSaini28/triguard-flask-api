"""Strict API contracts and domain validation for TriGuard."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplyChainCase(BaseModel):
    """A single case supplied by a planner or an upstream system."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str | None = Field(default=None, max_length=80)
    medicine_name: Annotated[str, Field(min_length=2, max_length=100)]
    medicine_criticality: Annotated[int, Field(ge=1, le=5)]
    cold_chain_required: bool
    supplier_id: Annotated[str, Field(min_length=1, max_length=80)]
    destination_facility: Annotated[str, Field(min_length=2, max_length=160)]
    supplier_on_time_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    supplier_fill_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    lead_time_days: Annotated[int, Field(ge=0, le=180)]
    lead_time_variability: Annotated[float, Field(ge=0.0, le=90.0)]
    route_delay_days: Annotated[float, Field(ge=0.0, le=90.0)]
    weather_risk_score: Annotated[int, Field(ge=0, le=10)]
    demand_spike_factor: Annotated[float, Field(ge=0.0, le=10.0)]
    current_stock_days: Annotated[int, Field(ge=0, le=365)]
    warehouse_utilization: Annotated[float, Field(ge=0.0, le=100.0)]

    @field_validator("medicine_name", "supplier_id", "destination_facility")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    def model_features(self) -> dict[str, object]:
        """Return only the ML features in the representation expected by model V2."""
        values = self.model_dump(exclude={"case_id"})
        values["cold_chain_required"] = int(values["cold_chain_required"])
        return values


class OperationalSignal(BaseModel):
    name: str
    direction: str
    detail: str


class PredictionResult(BaseModel):
    request_id: UUID
    scored_at: datetime
    case_id: str | None
    model_version: str
    risk_probability: float = Field(ge=0.0, le=1.0)
    risk_band: str
    predicted_disruption: bool
    classification_threshold: float
    threshold_margin: float
    review_required: bool
    triage_action: str
    severity: str
    response_sla: str
    recommended_actions: list[str]
    operational_signals: list[OperationalSignal]
    data_quality_flags: list[str]


class BatchPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cases: list[SupplyChainCase] = Field(min_length=1)


class BatchPredictionResponse(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    total_cases: int
    summary: dict[str, int]
    predictions: list[PredictionResult]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str | None
    api_key_required: bool


class DriftFeatureResult(BaseModel):
    feature: str
    baseline_mean: float | None = None
    observed_mean: float | None = None
    standardized_mean_shift: float | None = None
    status: str


class MonitoringResponse(BaseModel):
    assessed_cases: int
    overall_status: str
    feature_checks: list[DriftFeatureResult]
