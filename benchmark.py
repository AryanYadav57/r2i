"""Reproducible paired benchmark for classical and quantum-inspired R2I routes."""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from pathlib import Path

import networkx as nx

from candidate_routes import optimize_routes
from r2i_engine import load_network, estimate_edge_metrics
from traffic_provider import get_traffic_snapshot


def run(graph_path: str, output_dir: str, pairs: int = 30, seed: int = 42) -> list[dict]:
    graph = load_network(graph_path)
    nodes = sorted(graph.nodes, key=str)
    rng = random.Random(seed)
    scenarios = ["Normal conditions", "Peak bottleneck", "Incident / road closure", "Stale / missing traffic"]
    rows = []
    for pair_id in range(pairs):
        start = rng.choice(nodes)
        end = rng.choice(nodes)
        if start == end:
            continue
        for scenario_name in scenarios:
            scenario = get_traffic_snapshot(scenario_name)
            started = time.perf_counter()
            try:
                result = optimize_routes(graph, start, end, eco_priority=0.3, seed=seed + pair_id,
                    max_detour_ratio=1.7, max_failure_probability=0.5,
                    scenario_delays=scenario.delay_by_highway, closed_highways=scenario.closed_highways)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                rows.append({"pair_id": pair_id, "scenario": scenario_name, "status": "no_path"})
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            for method, path, stats in (
                ("classical_fastest", result["standard_path"], result["standard"]),
                ("classical_weighted_argmin", result["classical_weighted_path"], result["classical_weighted"]),
                ("qubo_simulated_annealing", result["eco_path"], result["eco"]),
            ):
                rows.append({"pair_id": pair_id, "scenario": scenario_name, "method": method,
                    "status": "ok", "start": str(start), "end": str(end),
                    "distance_km": stats["distance_km"], "travel_time_min": stats["travel_time_min"],
                    "carbon_g_estimate": stats["carbon_g"], "congestion_exposure": stats["congestion_exposure"],
                    "failure_probability_estimate": stats["failure_probability"], "path_edges": len(path)-1,
                    "candidate_count": result["candidate_count"], "solver_runtime_ms": result["solver"]["runtime_ms"],
                    "end_to_end_ms": elapsed_ms, "seed": seed + pair_id,
                    "qubo_selected_index": result["selected_candidate"],
                    "qubo_matches_exact_argmin": result["solver"]["selected_index"] == result["solver"]["classical_argmin_index"]})

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if rows:
        with (output / "benchmark_records.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
            writer.writeheader()
            writer.writerows(rows)
    ok = [row for row in rows if row.get("status") == "ok"]
    summary = {}
    for method in sorted({row["method"] for row in ok}):
        subset = [row for row in ok if row["method"] == method]
        latencies = sorted(row["end_to_end_ms"] for row in subset)
        summary[method] = {
            "runs": len(subset),
            "valid_route_rate": sum(row["status"] == "ok" for row in subset) / max(1, len(subset)),
            "median_end_to_end_ms": statistics.median(latencies),
            "p95_end_to_end_ms": latencies[min(len(latencies)-1, int(0.95 * len(latencies)))],
            "mean_travel_time_min": statistics.mean(row["travel_time_min"] for row in subset),
            "mean_carbon_g_estimate": statistics.mean(row["carbon_g_estimate"] for row in subset),
        }
    summary_payload = {"seed": seed, "od_pairs": pairs, "scenarios": scenarios,
        "note": "Emission, congestion, and failure figures are model estimates; QUBO uses a classical simulated-annealing heuristic.",
        "methods": summary}
    (output / "benchmark_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", default="bengaluru_grid.graphml")
    parser.add_argument("--output", default="output/benchmark")
    parser.add_argument("--pairs", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    records = run(args.graph, args.output, args.pairs, args.seed)
    print(f"Wrote {len(records)} paired benchmark records to {args.output}")
