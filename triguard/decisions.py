"""Transparent operational policies kept separate from the ML classifier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageDecision:
    action: str
    severity: str
    response_sla: str
    playbook: list[str]


PLAYBOOKS: dict[str, TriageDecision] = {
    "MONITOR": TriageDecision(
        action="MONITOR", severity="low", response_sla="Next routine review",
        playbook=[
            "Continue routine supplier and inventory monitoring.",
            "Reassess if the delivery commitment or stock cover changes.",
        ],
    ),
    "REVIEW": TriageDecision(
        action="REVIEW", severity="moderate", response_sla="Within 1 business day",
        playbook=[
            "Verify the supplier commitment and latest dispatch status.",
            "Confirm stock on hand and planned consumption with the destination facility.",
            "Prepare an alternate transport or replenishment option.",
        ],
    ),
    "ESCALATE TO PLANNER": TriageDecision(
        action="ESCALATE TO PLANNER", severity="high", response_sla="Within 4 hours",
        playbook=[
            "Alert the district or regional supply planner.",
            "Reserve alternate inventory and transport capacity.",
            "Contact the supplier for an updated delivery commitment.",
            "Track this case until the risk is resolved or downgraded.",
        ],
    ),
    "INTERVENE NOW": TriageDecision(
        action="INTERVENE NOW", severity="critical", response_sla="Immediately",
        playbook=[
            "Activate the emergency replenishment process.",
            "Expedite or reroute the shipment and notify the destination facility.",
            "Escalate to the incident commander and record the intervention.",
            "Check cold-chain continuity where applicable.",
        ],
    ),
}


def assign_triage(risk_probability: float, criticality: int, stock_days: int) -> TriageDecision:
    """Apply the documented triage policy; this is intentionally deterministic."""
    if risk_probability >= 0.75 and criticality >= 4 and stock_days <= 5:
        return PLAYBOOKS["INTERVENE NOW"]
    if risk_probability >= 0.60:
        return PLAYBOOKS["ESCALATE TO PLANNER"]
    if risk_probability >= 0.35:
        return PLAYBOOKS["REVIEW"]
    return PLAYBOOKS["MONITOR"]


def risk_band(risk_probability: float) -> str:
    if risk_probability >= 0.75:
        return "critical"
    if risk_probability >= 0.60:
        return "high"
    if risk_probability >= 0.35:
        return "moderate"
    return "low"
