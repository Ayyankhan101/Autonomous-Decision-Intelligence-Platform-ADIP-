"""Runtime policy positions (enhancement 2 — policy sandbox for ethical trade-offs).

Three pre-registered governance positions with fixed objective weights; the operator
switches position mid-scenario from the dashboard. Changes apply to new decisions
unless the operator explicitly re-optimises active incidents.

Setting A — RESPONSE_TIME: minimise arrival time (baseline allocation).
Setting B — EQUITY: prioritise historically underserved neighbourhoods — incidents in
    underserved zones are raised one priority step at decision time.
Setting C — ECO: prefer the vehicle with the highest eco_score (electric-first).
"""
from __future__ import annotations

from jevcity.schemas import PolicyPosition, Priority, Zone

# Pre-registered objective weights (relative: response_time / equity / emissions).
POSITION_WEIGHTS: dict[PolicyPosition, dict[str, float]] = {
    PolicyPosition.RESPONSE_TIME: {
        "response_time": 1.0,
        "equity": 0.0,
        "emissions": 0.0,
    },
    PolicyPosition.EQUITY: {
        "response_time": 0.0,
        "equity": 1.0,
        "emissions": 0.0,
    },
    PolicyPosition.ECO: {
        "response_time": 0.0,
        "equity": 0.0,
        "emissions": 1.0,
    },
}

# Historically underserved neighbourhoods (city equity configuration).
UNDERSERVED_ZONES = frozenset({Zone.NORTH, Zone.WEST})

_PRIORITY_STEP_UP: dict[Priority, Priority] = {
    Priority.LOW: Priority.MEDIUM,
    Priority.MEDIUM: Priority.HIGH,
    Priority.HIGH: Priority.CRITICAL,
    Priority.CRITICAL: Priority.CRITICAL,
}


def weights_for(position: PolicyPosition) -> dict[str, float]:
    return dict(POSITION_WEIGHTS[position])


def equity_step_up(priority: Priority) -> Priority:
    """EQUITY position: one-step priority raise for underserved zones (capped)."""
    return _PRIORITY_STEP_UP[priority]
