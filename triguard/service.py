"""Model-serving layer: reproducible loading, scoring, guardrails and auditing."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import joblib
import pandas as pd

from .audit import AuditLogger
from .config import Settings, settings
from .decisions import assign_triage, risk_band
from .monitoring import CATEGORICAL_FEATURES, NUMERIC_FEATURES, load_baseline
from .schemas import OperationalSignal, PredictionResult, SupplyChainCase


@lru_cache(maxsize=1)
def _load_artifacts(model_path: str, metadata_path: str) -> tuple[Any, dict[str, Any]]:
    model_file = Path(model_path)
    metadata_file = Path(metadata_path)
    if not model_file.exists() or not metadata_file.exists():
        raise FileNotFoundError("Model artifacts are missing. Train or mount a verified V2 model first.")
    model = joblib.load(model_file)
    with metadata_file.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    required = {"model_version", "feature_columns", "operating_threshold"}
    missing = required - set(metadata)
    if missing:
        raise ValueError(f"Model metadata is missing required fields: {sorted(missing)}")
    expected_hash = metadata.get("artifact_sha256")
    if expected_hash:
        actual_hash = hashlib.sha256(model_file.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise ValueError("Model artifact checksum does not match its approved metadata.")
    return model, metadata


class ModelService:
    """The single application entry point for model scoring."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.audit_logger = AuditLogger(app_settings.audit_log_path)

    @property
    def artifacts(self) -> tuple[Any, dict[str, Any]]:
        return _load_artifacts(str(self.settings.model_path), str(self.settings.metadata_path))

    @property
    def metadata(self) -> dict[str, Any]:
        return self.artifacts[1]

    def health(self) -> tuple[bool, str | None]:
        try:
            return True, str(self.metadata["model_version"])
        except (FileNotFoundError, ValueError, OSError):
            return False, None

    def predict(self, case: SupplyChainCase, request_id: UUID | None = None, source: str = "local") -> PredictionResult:
        request_id = request_id or uuid4()
        model, metadata = self.artifacts
        features = case.model_features()
        feature_columns = metadata["feature_columns"]
        input_frame = pd.DataFrame([{feature: features[feature] for feature in feature_columns}], columns=feature_columns)
        probability = float(model.predict_proba(input_frame)[0, 1])
        threshold = float(metadata["operating_threshold"])
        decision = assign_triage(probability, case.medicine_criticality, case.current_stock_days)
        result = PredictionResult(
            request_id=request_id,
            scored_at=datetime.now(UTC),
            case_id=case.case_id,
            model_version=str(metadata["model_version"]),
            risk_probability=round(probability, 4),
            risk_band=risk_band(probability),
            predicted_disruption=probability >= threshold,
            classification_threshold=threshold,
            threshold_margin=round(abs(probability - threshold), 4),
            review_required=abs(probability - threshold) < 0.08,
            triage_action=decision.action,
            severity=decision.severity,
            response_sla=decision.response_sla,
            recommended_actions=decision.playbook,
            operational_signals=self._operational_signals(case),
            data_quality_flags=self._data_quality_flags(case),
        )
        self._audit(result, source)
        return result

    def _operational_signals(self, case: SupplyChainCase) -> list[OperationalSignal]:
        """Rule-based planner signals; these are not represented as causal model explanations."""
        signals: list[OperationalSignal] = []
        if case.current_stock_days <= 5:
            signals.append(OperationalSignal(name="Low stock cover", direction="increases urgency", detail=f"Only {case.current_stock_days} days of cover remain."))
        if case.supplier_on_time_rate < 0.75:
            signals.append(OperationalSignal(name="Supplier reliability", direction="increases risk", detail=f"On-time rate is {case.supplier_on_time_rate:.0%}."))
        if case.supplier_fill_rate < 0.80:
            signals.append(OperationalSignal(name="Supplier fill rate", direction="increases risk", detail=f"Fill rate is {case.supplier_fill_rate:.0%}."))
        if case.route_delay_days >= 3:
            signals.append(OperationalSignal(name="Route delay", direction="increases risk", detail=f"Reported delay is {case.route_delay_days:.1f} days."))
        if case.weather_risk_score >= 7:
            signals.append(OperationalSignal(name="Weather exposure", direction="increases risk", detail=f"Weather score is {case.weather_risk_score}/10."))
        if case.demand_spike_factor >= 1.30:
            signals.append(OperationalSignal(name="Demand spike", direction="increases risk", detail=f"Demand is {case.demand_spike_factor:.2f}× the normal baseline."))
        if case.warehouse_utilization >= 90:
            signals.append(OperationalSignal(name="Warehouse utilization", direction="increases risk", detail=f"Warehouse is {case.warehouse_utilization:.0f}% utilized."))
        if not signals:
            signals.append(OperationalSignal(name="No material operational trigger", direction="neutral", detail="Inputs are within the routine planner review range."))
        return signals[:5]

    def _data_quality_flags(self, case: SupplyChainCase) -> list[str]:
        try:
            baseline = load_baseline(self.settings.baseline_data_path)
        except (FileNotFoundError, OSError, pd.errors.ParserError):
            return ["Training reference data is unavailable; input-distribution checks were skipped."]
        flags: list[str] = []
        features = case.model_features()
        for feature in CATEGORICAL_FEATURES:
            if str(features[feature]) not in set(baseline[feature].dropna().astype(str)):
                flags.append(f"{feature} was not observed in the training reference; model confidence may be limited.")
        for feature in NUMERIC_FEATURES:
            series = pd.to_numeric(baseline[feature], errors="coerce").dropna()
            lower, upper = series.quantile([0.01, 0.99])
            value = float(features[feature])
            if value < lower or value > upper:
                flags.append(f"{feature} is outside the 1st–99th percentile of the training reference.")
        return flags

    def _audit(self, result: PredictionResult, source: str) -> None:
        # Case identifiers are one-way hashed before persistence. Raw input data is never logged here.
        case_fingerprint = None
        if result.case_id:
            case_fingerprint = hashlib.sha256(result.case_id.encode("utf-8")).hexdigest()[:16]
        self.audit_logger.record({
            "event_type": "prediction_scored",
            "request_id": str(result.request_id),
            "source": source,
            "case_fingerprint": case_fingerprint,
            "model_version": result.model_version,
            "risk_band": result.risk_band,
            "triage_action": result.triage_action,
            "review_required": result.review_required,
        })
