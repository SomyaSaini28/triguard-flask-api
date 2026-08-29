from pathlib import Path

from pydantic import ValidationError

from triguard.config import settings
from triguard.schemas import SupplyChainCase
from triguard.service import ModelService


def sample_case() -> SupplyChainCase:
    return SupplyChainCase(
        case_id="TEST-001", medicine_name="Insulin", medicine_criticality=5,
        cold_chain_required=True, supplier_id="S2", destination_facility="District Hospital Jaipur",
        supplier_on_time_rate=0.68, supplier_fill_rate=0.72, lead_time_days=8,
        lead_time_variability=4.5, route_delay_days=3.8, weather_risk_score=8,
        demand_spike_factor=1.4, current_stock_days=3, warehouse_utilization=88,
    )


def test_service_scores_case_and_writes_deidentified_audit_event(tmp_path: Path):
    local_settings = settings.__class__(
        model_path=settings.model_path,
        metadata_path=settings.metadata_path,
        baseline_data_path=settings.baseline_data_path,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    result = ModelService(local_settings).predict(sample_case(), source="test")

    assert 0.0 <= result.risk_probability <= 1.0
    assert result.model_version == "v3"
    assert result.triage_action in {"MONITOR", "REVIEW", "ESCALATE TO PLANNER", "INTERVENE NOW"}
    audit_text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "TEST-001" not in audit_text
    assert "prediction_scored" in audit_text


def test_schema_rejects_unapproved_model_fields():
    payload = sample_case().model_dump()
    payload["safety_stock_gap"] = 7

    try:
        SupplyChainCase.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("Unexpected fields must be rejected")
