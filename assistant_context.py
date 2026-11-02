"""Build a minimal, allowlisted context for the optional route assistant."""

from __future__ import annotations

from typing import Any


_METRIC_FIELDS = (
    "distance_km",
    "travel_time_min",
    "carbon_g",
    "fuel_ml",
    "energy_kwh",
    "cost_inr",
)


def _metric_summary(stats: dict[str, Any] | None) -> dict[str, float | None]:
    stats = stats or {}
    summary: dict[str, float | None] = {}
    for field in _METRIC_FIELDS:
        value = stats.get(field)
        try:
            summary[field] = float(value) if value is not None else None
        except (TypeError, ValueError):
            summary[field] = None
    return summary


def build_route_context(result: dict[str, Any]) -> dict[str, Any]:
    """Return only user-facing trip labels and computed comparison facts.

    Route node IDs, path coordinates, credentials, and unrelated session state
    are intentionally excluded.
    """
    metrics = result.get("metrics") or {}
    optimizer = result.get("optimizer") or {}
    source = str(result.get("source") or "Unknown route source")
    normal_stats = _metric_summary(result.get("standard"))
    r2i_stats = _metric_summary(result.get("eco"))
    normal_distance = normal_stats.get("distance_km")
    r2i_distance = r2i_stats.get("distance_km")
    distance_delta = (
        normal_distance - r2i_distance
        if normal_distance is not None and r2i_distance is not None
        else None
    )
    distance_delta_percent = (
        distance_delta / normal_distance * 100
        if distance_delta is not None and normal_distance
        else None
    )
    has_local_optimizer = bool(optimizer)
    if has_local_optimizer:
        r2i_method = "Local OSM graph candidate routing with a one-hot QUBO selector"
        algorithm = {
            "pipeline": [
                "Snap origin and destination to nearby road-graph nodes; the local-graph branch is used when both are within 800 m.",
                "Remove closed highways and collapse parallel directed edges to the edge with the lowest estimated travel time.",
                "Find a fastest-time reference route, then generate up to 10 loop-free alternatives ordered by estimated travel time.",
                "Filter candidates by maximum detour, reliability-risk threshold, and optional trip-time limit.",
                "Min-max normalize candidate travel time, estimated carbon, congestion exposure, failure risk, and detour; combine them with the eco/time weights supplied below.",
                "Encode the candidate scores as an exactly-one QUBO, run bounded CPU simulated annealing, and compare its result with exact classical argmin as a validity/quality safeguard.",
            ],
            "distance_is_direct_objective": False,
            "distance_indirect_effect": "Route length affects edge-derived fuel/energy, emissions, and cost estimates, which can influence the composite score.",
            "quantum_hardware_used": False,
        }
    else:
        r2i_method = "OSRM road-route alternatives scored by the R2I time/emissions trade-off"
        algorithm = {
            "pipeline": [
                "Use OSRM road-route alternatives outside the bundled local graph.",
                "Score each available alternative with eco_priority × travel_time_min + (1 - eco_priority) × carbon_g / 10.",
                "Estimate fuel, emissions, and cost from route distance and the selected vehicle profile because local road-edge attributes are unavailable.",
            ],
            "distance_is_direct_objective": False,
            "distance_indirect_effect": "OSRM alternatives are scored with travel time and estimated carbon; carbon is estimated from route distance and vehicle profile.",
            "quantum_hardware_used": False,
        }

    context: dict[str, Any] = {
        "trip": {
            "origin": str(result.get("start_label") or "Not available"),
            "destination": str(result.get("end_label") or "Not available"),
            "vehicle": "EV" if metrics.get("is_ev") else "ICE",
            "eco_time_priority_0_to_1": _number(result.get("eco_priority")),
            "traffic_scenario": str(result.get("traffic_scenario") or "Not available"),
            "route_source": source,
            "normal_baseline_provider": "Google Routes API" if source == "Google Maps baseline" else "OSRM/local route baseline",
            "r2i_method": r2i_method,
        },
        "routes": {
            "normal_baseline": normal_stats,
            "r2i_selected": r2i_stats,
        },
        "route_length_comparison": {
            "normal_minus_r2i_km": _number(distance_delta),
            "percent_shorter_than_normal": _number(distance_delta_percent),
            "explanation": "A shorter length is an outcome of selecting among road-route candidates; distance is not a direct objective in the local QUBO score.",
        },
        "computed_changes": {
            "carbon_saved_vs_normal_g": _number(metrics.get("carbon_s")),
            "fuel_saved_vs_normal_ml": _number(metrics.get("fuel_s")),
            "energy_saved_vs_normal_kwh": _number(metrics.get("energy_s")),
            "money_saved_vs_normal_inr": _number(metrics.get("money_s")),
            "r2i_minus_normal_time_min": _number(metrics.get("time_diff")),
        },
        "data_notes": {
            "traffic_source": str(result.get("traffic_source") or "Not available"),
            "traffic_confidence": _number(result.get("traffic_confidence")),
            "traffic_observed_at": str(result.get("traffic_observed_at") or "Not available"),
            "has_live_traffic": bool(result.get("has_live_traffic", False)),
            "metrics_are_estimates": True,
            "same_route": bool(metrics.get("same_route", False)),
        },
        "optimizer": {
            "solver": str(optimizer.get("solver") or "Not available"),
            "fallback_used": bool(optimizer.get("fallback", False)),
            "candidate_count": _integer(result.get("candidate_count")),
            "runtime_ms": _number(result.get("routing_runtime_ms")),
            "objective_weights": _numeric_map(result.get("weights")),
            "selected_objective_components": _numeric_map(result.get("objective_components")),
            "maximum_detour_ratio": _number(result.get("max_detour_ratio")),
            "maximum_failure_probability": _number(result.get("max_failure_probability")),
            "maximum_trip_time_min": _number(result.get("max_trip_time_min")),
        },
        "algorithm_explanation": algorithm,
    }
    return context


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _numeric_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    numeric: dict[str, float] = {}
    for key, item in value.items():
        try:
            numeric[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return numeric
