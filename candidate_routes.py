"""Feasible alternative generation and route-level multi-objective evaluation."""
from __future__ import annotations

import time
import networkx as nx

from r2i_engine import (
    _edge_options, _traffic_multiplier_for_edge, estimate_edge_metrics,
    ROAD_CONGESTION, ROAD_SPEED_KMH,
)
from quantum_inspired import solve_route_qubo


def _highway(data):
    value = data.get("highway", "residential")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "residential"
    return str(value).strip("[]'\"").split(",")[0]


def _collapse_for_paths(graph, traffic_multiplier, traffic_segments, closed_highways, scenario_delays):
    simple = nx.DiGraph()
    simple.add_nodes_from(graph.nodes(data=True))
    for u, v, data in graph.edges(data=True):
        highway = _highway(data)
        if highway in closed_highways or str(data.get("closed", "")).lower() == "true":
            continue
        edge_mult = _traffic_multiplier_for_edge(graph, u, v, traffic_multiplier, traffic_segments)
        edge_mult *= scenario_delays.get(highway, 1.0)
        metrics = estimate_edge_metrics(data, "ICE", edge_mult)
        previous = simple.get_edge_data(u, v)
        if previous is None or metrics["travel_time_min"] < previous["time"]:
            simple.add_edge(u, v, time=metrics["travel_time_min"], source_data=data, edge_mult=edge_mult)
    return simple


def _evaluate(graph, path, *, vehicle_type, edge_scale, traffic_multiplier, traffic_segments,
              scenario_delays, reliability_by_highway):
    totals = {"distance_km": 0.0, "travel_time_min": 0.0, "fuel_ml": 0.0,
              "energy_kwh": 0.0, "carbon_g": 0.0, "cost_inr": 0.0,
              "congestion_exposure": 0.0, "failure_probability": 0.0}
    for u, v in zip(path, path[1:]):
        options = _edge_options(graph, graph.get_edge_data(u, v))
        data = min(options, key=lambda item: float(item.get("length", 0) or 0))
        highway = _highway(data)
        multiplier = _traffic_multiplier_for_edge(graph, u, v, traffic_multiplier, traffic_segments)
        multiplier *= scenario_delays.get(highway, 1.0)
        edge_metrics = estimate_edge_metrics(data, vehicle_type, multiplier)
        edge_metrics["travel_time_min"] *= edge_scale
        for key in ("distance_km", "travel_time_min", "fuel_ml", "energy_kwh", "carbon_g", "cost_inr"):
            totals[key] += edge_metrics[key]
        congestion = min(1.0, max(0.0, ROAD_CONGESTION.get(highway, 0.12) * multiplier))
        totals["congestion_exposure"] += edge_metrics["distance_km"] * congestion
        failure = min(0.95, max(0.0, reliability_by_highway.get(highway, 0.005)))
        totals["failure_probability"] = 1 - (1 - totals["failure_probability"]) * (1 - failure)
    return totals


def _normalize(values):
    low, high = min(values), max(values)
    if high - low < 1e-12:
        return [0.0 for _ in values]
    return [(min(1.0, max(0.0, value - low) / (high - low))) for value in values]


def optimize_routes(graph, source, target, *, vehicle_type="ICE", eco_priority=0.3,
                    k=10, seed=42, max_detour_ratio=1.5, max_failure_probability=0.5,
                    max_time_min=None, traffic_multiplier=1.0, traffic_segments=None,
                    scenario_delays=None, closed_highways=(), reliability_by_highway=None,
                    anneal_timeout_s=0.05):
    """Compare fastest route, classical weighted choice, and QUBO annealing."""
    started = time.perf_counter()
    scenario_delays = scenario_delays or {}
    reliability_by_highway = reliability_by_highway or {}
    graph_view = _collapse_for_paths(graph, traffic_multiplier, traffic_segments,
                                     set(closed_highways), scenario_delays)
    if source not in graph_view or target not in graph_view:
        raise nx.NetworkXNoPath(f"No available route from {source} to {target}")
    fastest = nx.shortest_path(graph_view, source, target, weight="time")
    fastest_stats = _evaluate(graph, fastest, vehicle_type=vehicle_type, edge_scale=1.0,
        traffic_multiplier=traffic_multiplier, traffic_segments=traffic_segments,
        scenario_delays=scenario_delays, reliability_by_highway=reliability_by_highway)
    shortest_time = fastest_stats["travel_time_min"]

    paths = []
    limit = max(1, min(int(k), 30))
    try:
        for path in nx.shortest_simple_paths(graph_view, source, target, weight="time"):
            paths.append(path)
            if len(paths) >= limit:
                break
    except (nx.NetworkXNoPath, nx.NetworkXNotImplemented):
        paths = [fastest]
    if not paths:
        paths = [fastest]

    candidates = []
    for path in paths:
        stats = _evaluate(graph, path, vehicle_type=vehicle_type, edge_scale=1.0,
            traffic_multiplier=traffic_multiplier, traffic_segments=traffic_segments,
            scenario_delays=scenario_delays, reliability_by_highway=reliability_by_highway)
        detour = stats["travel_time_min"] / max(shortest_time, 1e-9)
        if detour > max_detour_ratio or stats["failure_probability"] > max_failure_probability:
            continue
        if max_time_min is not None and stats["travel_time_min"] > max_time_min:
            continue
        candidates.append({"path": path, "stats": stats, "detour_ratio": detour})
    if not candidates:
        raise ValueError("No route satisfies the selected detour, travel-time, and reliability constraints.")

    features = {
        "time": [c["stats"]["travel_time_min"] for c in candidates],
        "carbon": [c["stats"]["carbon_g"] for c in candidates],
        "congestion": [c["stats"]["congestion_exposure"] for c in candidates],
        "risk": [c["stats"]["failure_probability"] for c in candidates],
        "detour": [c["detour_ratio"] for c in candidates],
    }
    norm = {key: _normalize(vals) for key, vals in features.items()}
    eco = min(max(float(eco_priority), 0.0), 1.0)
    weights = {"time": 0.65 * eco + 0.1, "carbon": 0.75 * (1 - eco),
               "congestion": 0.2 * (1 - eco) + 0.1 * eco, "risk": 0.1, "detour": 0.1}
    total_weight = sum(weights.values())
    weights = {key: value / total_weight for key, value in weights.items()}
    for i, candidate in enumerate(candidates):
        candidate["objective"] = sum(weights[key] * norm[key][i] for key in weights)
        candidate["objective_components"] = {key: weights[key] * norm[key][i] for key in weights}

    scores = [candidate["objective"] for candidate in candidates]
    classical_index = min(range(len(scores)), key=lambda i: (scores[i], i))
    solver = solve_route_qubo(scores, seed=seed, timeout_s=anneal_timeout_s)
    selected = solver["selected_index"]
    classical = candidates[classical_index]
    quantum = candidates[selected]
    return {
        "standard_path": fastest, "standard": fastest_stats,
        "eco_path": quantum["path"], "eco": quantum["stats"],
        "classical_weighted_path": classical["path"], "classical_weighted": classical["stats"],
        "candidates": candidates, "candidate_count": len(candidates),
        "selected_candidate": selected, "weights": weights,
        "selected_objective": quantum["objective"],
        "objective_components": quantum["objective_components"],
        "solver": solver, "routing_runtime_ms": (time.perf_counter() - started) * 1000,
        "source": "Local R2I candidate routes", "path_coordinates": False,
        "savings": {
            "carbon_g": fastest_stats["carbon_g"] - quantum["stats"]["carbon_g"],
            "fuel_ml": fastest_stats["fuel_ml"] - quantum["stats"]["fuel_ml"],
            "energy_kwh": fastest_stats["energy_kwh"] - quantum["stats"]["energy_kwh"],
            "money_inr": fastest_stats["cost_inr"] - quantum["stats"]["cost_inr"],
            "time_diff": quantum["stats"]["travel_time_min"] - fastest_stats["travel_time_min"],
        },
    }
