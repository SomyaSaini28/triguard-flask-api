"""Input-distribution checks for early warning of data drift."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import settings
from .schemas import DriftFeatureResult, SupplyChainCase


CATEGORICAL_FEATURES = {"medicine_name", "supplier_id", "destination_facility"}
NUMERIC_FEATURES = [
    "medicine_criticality", "cold_chain_required", "supplier_on_time_rate", "supplier_fill_rate",
    "lead_time_days", "lead_time_variability", "route_delay_days", "weather_risk_score",
    "demand_spike_factor", "current_stock_days", "warehouse_utilization",
]


@lru_cache(maxsize=4)
def load_baseline(path: str | Path | None = None) -> pd.DataFrame:
    """Load a baseline by explicit path so app instances do not share hidden settings."""
    baseline_path = Path(path) if path is not None else settings.baseline_data_path
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline data not found: {baseline_path}")
    return pd.read_csv(baseline_path)


def assess_input_drift(
    cases: list[SupplyChainCase],
    baseline_path: str | Path | None = None,
) -> tuple[str, list[DriftFeatureResult]]:
    """Compare batch means to the training reference using a simple transparent guardrail.

    This is an input-quality signal, not a claim of model-performance drift. Performance
    drift requires delayed real-world outcome labels and is intentionally kept separate.
    """
    baseline = load_baseline(baseline_path)
    observed = pd.DataFrame([case.model_features() for case in cases])
    checks: list[DriftFeatureResult] = []

    for feature in NUMERIC_FEATURES:
        reference = pd.to_numeric(baseline[feature], errors="coerce").dropna()
        observed_values = pd.to_numeric(observed[feature], errors="coerce").dropna()
        baseline_mean = float(reference.mean())
        observed_mean = float(observed_values.mean())
        standard_deviation = float(reference.std(ddof=0))
        shift = abs(observed_mean - baseline_mean) / standard_deviation if standard_deviation else 0.0
        status = "alert" if shift >= 1.0 else "watch" if shift >= 0.5 else "ok"
        checks.append(DriftFeatureResult(
            feature=feature,
            baseline_mean=round(baseline_mean, 4),
            observed_mean=round(observed_mean, 4),
            standardized_mean_shift=round(shift, 4),
            status=status,
        ))

    for feature in sorted(CATEGORICAL_FEATURES):
        known_values = set(baseline[feature].dropna().astype(str))
        unknown_count = int((~observed[feature].astype(str).isin(known_values)).sum())
        checks.append(DriftFeatureResult(
            feature=feature,
            status="alert" if unknown_count else "ok",
        ))

    overall = "alert" if any(check.status == "alert" for check in checks) else (
        "watch" if any(check.status == "watch" for check in checks) else "ok"
    )
    return overall, checks
