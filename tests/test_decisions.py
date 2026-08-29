from triguard.decisions import assign_triage, risk_band


def test_critical_case_requires_immediate_intervention():
    decision = assign_triage(0.75, criticality=4, stock_days=5)

    assert decision.action == "INTERVENE NOW"
    assert decision.response_sla == "Immediately"


def test_high_risk_without_low_stock_is_escalated_not_immediate():
    assert assign_triage(0.80, criticality=5, stock_days=6).action == "ESCALATE TO PLANNER"


def test_risk_bands_match_documented_boundaries():
    assert risk_band(0.34) == "low"
    assert risk_band(0.35) == "moderate"
    assert risk_band(0.60) == "high"
    assert risk_band(0.75) == "critical"
