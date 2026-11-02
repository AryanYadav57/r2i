"""Paired benchmark: Google traffic-aware route, classic R2I, R2I QUBO selector."""
from __future__ import annotations

import csv
import json
import math
import statistics
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from candidate_routes import optimize_routes
from r2i_engine import calculate_google_baseline, calculate_route_comparison, load_network


LANDMARKS = {
    "Sony World Signal": (12.932, 77.623),
    "Wipro Park": (12.930, 77.620),
    "Koramangala 5th Block": (12.938, 77.630),
    "Forum Mall": (12.933, 77.625),
    "St John's Hospital": (12.940, 77.618),
    "Koramangala 1st Block": (12.928, 77.628),
    "Koramangala 3rd Block": (12.935, 77.621),
    "Koramangala 6th Block": (12.931, 77.635),
}
OD_PAIRS = [
    ("Sony World Signal", "St John's Hospital"),
    ("Wipro Park", "Forum Mall"),
    ("Koramangala 1st Block", "Koramangala 6th Block"),
    ("Forum Mall", "St John's Hospital"),
    ("Koramangala 3rd Block", "Wipro Park"),
    ("Koramangala 5th Block", "Sony World Signal"),
]


def _key() -> str:
    with Path(".streamlit/secrets.toml").open("rb") as handle:
        secrets = tomllib.load(handle)
    return secrets.get("google_maps_server_api_key") or secrets.get("google_maps_api_key", "")


def _nearest(graph, coords):
    lat, lon = coords
    return min(graph.nodes, key=lambda n: (float(graph.nodes[n]["x"])-lon)**2 + (float(graph.nodes[n]["y"])-lat)**2)


def _snap_m(graph, node, coords):
    lat, lon = coords
    dlat = (float(graph.nodes[node]["y"])-lat)*111_320
    dlon = (float(graph.nodes[node]["x"])-lon)*111_320*math.cos(math.radians(lat))
    return math.hypot(dlat, dlon)


def run(output_dir="output/benchmark_comparison", alpha=0.3, seed=42):
    graph = load_network("bengaluru_grid.graphml")
    for _, data in graph.nodes(data=True):
        data["x"] = float(data["x"])
        data["y"] = float(data["y"])
    api_key = _key()
    results = []
    for index, (origin, destination) in enumerate(OD_PAIRS, 1):
        start_coords, end_coords = LANDMARKS[origin], LANDMARKS[destination]
        start_node, end_node = _nearest(graph, start_coords), _nearest(graph, end_coords)
        if max(_snap_m(graph, start_node, start_coords), _snap_m(graph, end_node, end_coords)) > 800:
            results.append({"trip": index, "origin": origin, "destination": destination,
                            "status": "excluded", "reason": "Landmark is outside 800 m local graph snap limit"})
            continue
        google_started = time.perf_counter()
        try:
            google = calculate_google_baseline(start_coords, end_coords, api_key, "ICE")
        except Exception as error:
            results.append({"trip": index, "origin": origin, "destination": destination,
                            "status": "google_api_error", "reason": str(error)})
            continue
        google_api_ms = (time.perf_counter() - google_started)*1000
        common = {"traffic_multiplier": google["traffic_multiplier"],
                  "traffic_segments": google.get("traffic_segments", [])}
        classic_started = time.perf_counter()
        classical = calculate_route_comparison(graph, start_node, end_node,
            vehicle_type="ICE", alpha=alpha, **common)
        classical_ms = (time.perf_counter()-classic_started)*1000
        qi_started = time.perf_counter()
        qi = optimize_routes(graph, start_node, end_node, vehicle_type="ICE",
            eco_priority=alpha, seed=seed+index, max_detour_ratio=1.7,
            max_failure_probability=0.5, **common)
        qi_ms = (time.perf_counter()-qi_started)*1000
        candidate_argmin_index = min(range(qi["candidate_count"]),
            key=lambda i: (qi["candidates"][i]["objective"], i))
        candidate_argmin = qi["candidates"][candidate_argmin_index]
        methods = [
            ("Google Maps normal (traffic-aware)", google["stats"], None, google_api_ms),
            ("R2I classical eco route", classical["eco"], classical["eco_path"], classical_ms),
            ("R2I weighted candidate argmin", candidate_argmin["stats"], candidate_argmin["path"], qi_ms),
            ("R2I quantum-inspired selector", qi["eco"], qi["eco_path"], qi_ms),
        ]
        for method, metrics, path, elapsed in methods:
            results.append({"trip": index, "origin": origin, "destination": destination,
                "status": "ok", "method": method, "distance_km": metrics["distance_km"],
                "travel_time_min": metrics["travel_time_min"], "carbon_g_estimate": metrics["carbon_g"],
                "fuel_ml_estimate": metrics["fuel_ml"],
                "congestion_exposure_estimate": metrics.get("congestion_exposure"),
                "failure_probability_estimate": metrics.get("failure_probability"),
                "route_edges": len(path)-1 if path else None, "compute_or_api_ms": elapsed,
                "google_api_latency_ms": google_api_ms, "r2i_classic_latency_ms": classical_ms,
                "r2i_qi_latency_ms": qi_ms, "traffic_multiplier": google["traffic_multiplier"],
                "traffic_intervals": len(google.get("traffic_segments", [])),
                "qi_candidates": qi["candidate_count"], "qi_seed": qi["solver"]["seed"],
                "qi_solver_ms": qi["solver"]["runtime_ms"],
                "qi_final_matches_exact_candidate_argmin": qi["solver"]["selected_index"] == candidate_argmin_index,
                "raw_anneal_sample_feasible": qi["solver"]["annealed_feasible"],
                "raw_anneal_sample_matches_argmin": qi["solver"]["annealed_index"] == candidate_argmin_index})

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    record_path = output / "benchmark_records.csv"
    if results:
        fields = list(dict.fromkeys(field for row in results for field in row))
        with record_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)
    summary = _summarize(results, alpha, seed)
    (output / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "BENCHMARK_REPORT.md").write_text(_report(summary), encoding="utf-8")
    return summary


def _summarize(results, alpha, seed):
    usable = [row for row in results if row.get("status") == "ok"]
    by_method = {}
    for method in ("Google Maps normal (traffic-aware)", "R2I classical eco route", "R2I weighted candidate argmin", "R2I quantum-inspired selector"):
        rows = [row for row in usable if row["method"] == method]
        if not rows:
            continue
        by_method[method] = {key: statistics.mean(row[key] for row in rows)
            for key in ("distance_km", "travel_time_min", "carbon_g_estimate", "fuel_ml_estimate", "compute_or_api_ms")}
        by_method[method]["trips"] = len(rows)
        by_method[method]["median_compute_or_api_ms"] = statistics.median(row["compute_or_api_ms"] for row in rows)
        by_method[method]["max_compute_or_api_ms"] = max(row["compute_or_api_ms"] for row in rows)
    trip_results = {}
    for trip in sorted({r["trip"] for r in usable}):
        group = {r["method"]: r for r in usable if r["trip"] == trip}
        if len(group) == 4:
            g = group["Google Maps normal (traffic-aware)"]
            c = group["R2I classical eco route"]
            a = group["R2I weighted candidate argmin"]
            q = group["R2I quantum-inspired selector"]
            trip_results[str(trip)] = {"origin": g["origin"], "destination": g["destination"],
                "google_time_min": g["travel_time_min"], "classical_r2i_time_min": c["travel_time_min"],
                "qi_time_min": q["travel_time_min"], "classical_r2i_co2_g": c["carbon_g_estimate"],
                "candidate_argmin_time_min": a["travel_time_min"],
                "candidate_argmin_co2_g": a["carbon_g_estimate"],
                "qi_co2_g": q["carbon_g_estimate"], "qi_candidate_count": q["qi_candidates"]}
    qi_rows = [r for r in usable if r["method"] == "R2I quantum-inspired selector"]
    return {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "benchmark_type": "bounded live Google Routes API comparison; fixed OD set; ICE; same local graph for R2I variants",
        "requested_trips": len(OD_PAIRS), "successful_complete_trip_sets": len(trip_results),
        "seed": seed, "eco_time_alpha": alpha,
        "methods": by_method, "per_trip": trip_results,
        "failed_or_excluded": [r for r in results if r.get("status") != "ok"],
        "qi_final_equal_to_candidate_argmin_on_all_trips": all(r["qi_final_matches_exact_candidate_argmin"] for r in qi_rows),
        "raw_annealing_sample_feasible_rate": sum(r["raw_anneal_sample_feasible"] for r in qi_rows) / max(1, len(qi_rows)),
        "raw_annealing_sample_matches_argmin_rate": sum(r["raw_anneal_sample_matches_argmin"] for r in qi_rows) / max(1, len(qi_rows)),
        "limitations": ["Google traffic-aware routes use Google's network and traffic model; R2I routes use the bundled local graph, so map coverage and estimates differ.",
            "R2I emissions/fuel are model estimates, not measured vehicle telemetry.",
            "Google API latency includes network/API time; R2I latency is local algorithm compute and is not directly equivalent.",
            "The one-hot QUBO over complete candidate routes is equivalent to classical argmin; this benchmark cannot establish quantum speedup.",
            "Only a small fixed Koramangala trip set was used; findings are illustrative, not statistically generalizable."]}


def _report(summary):
    lines = ["# R2I Route Optimizer Benchmark Report", "",
        f"Generated (UTC): {summary['generated_utc']}", "",
        "## Executive summary", "",
        f"Successful complete trip sets: **{summary['successful_complete_trip_sets']} / {summary['requested_trips']}**. The comparison includes Google’s traffic-aware normal route, current classical R2I eco-routing, and R2I’s quantum-inspired candidate selector.", "",
        "This is a prototype comparison, not evidence of a quantum advantage. The one-hot QUBO has an exact classical argmin equivalent; see limitations.", "",
        "## Method", "",
        "- Fixed Koramangala landmark pairs; ICE profile; eco/time alpha `%.2f`; deterministic QI seed base `%d`." % (summary["eco_time_alpha"], summary["seed"]),
        "- One Google Routes API traffic-aware route request per included origin/destination pair. Its returned traffic duration and traffic intervals are passed to both R2I methods.",
        "- R2I classical result uses the existing weighted shortest-path eco objective. QI result generates up to 10 feasible local candidates, applies the shared objective and constraints, then runs a seeded simulated-annealing QUBO selector.",
        "- Results record route distance, estimated travel time, estimated fuel/CO₂, latency, traffic multiplier, candidate count, and solver diagnostics.", "",
        "## Mean results", "",
        "| Method | Trips | Mean distance (km) | Mean time (min) | Mean CO₂ estimate (g) | Mean fuel estimate (mL) | Mean latency (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for method, label in [("Google Maps normal (traffic-aware)", "Google Maps normal (traffic-aware)"),
        ("R2I classical eco route", "R2I classical eco route"),
        ("R2I weighted candidate argmin", "R2I weighted candidate argmin (same candidates)"),
        ("R2I quantum-inspired selector", "R2I quantum-inspired selector")]:
        stats = summary["methods"].get(method)
        if stats:
            lines.append(f"| {label} | {stats['trips']} | {stats['distance_km']:.2f} | {stats['travel_time_min']:.2f} | {stats['carbon_g_estimate']:.1f} | {stats['fuel_ml_estimate']:.1f} | {stats['compute_or_api_ms']:.1f} |")
    lines += ["", "Mean latency is not directly comparable: Google includes network/API time; R2I is local compute.", "",
        "## Per-trip comparison", "", "| Trip | Origin → destination | Google (min) | R2I classical (min / CO₂ g) | Candidate argmin (min / CO₂ g) | R2I QI (min / CO₂ g) | Candidates |", "|---:|---|---:|---:|---:|---:|"]
    for trip, r in summary["per_trip"].items():
        lines.append(f"| {trip} | {r['origin']} → {r['destination']} | {r['google_time_min']:.1f} | {r['classical_r2i_time_min']:.1f} / {r['classical_r2i_co2_g']:.1f} | {r['candidate_argmin_time_min']:.1f} / {r['candidate_argmin_co2_g']:.1f} | {r['qi_time_min']:.1f} / {r['qi_co2_g']:.1f} | {r['qi_candidate_count']} |")
    lines += ["", "## Interpretation", "",
        f"The safeguarded QI result equals exact argmin on the shared candidate set for all trips: **{summary['qi_final_equal_to_candidate_argmin_on_all_trips']}**. Raw annealing samples were feasible on **{summary['raw_annealing_sample_feasible_rate']:.0%}** of trips and matched exact argmin on **{summary['raw_annealing_sample_matches_argmin_rate']:.0%}**. The safeguarded final route uses exact classical argmin if the annealer misses or returns an invalid sample. This is expected for a one-hot QUBO and is not evidence of annealing superiority.", "",
        "Google is a useful real-world routing reference, but it is not a strict algorithmic control because its road graph, traffic estimates, routing objective, and map coverage differ from R2I's local OSM graph. Compare Google mainly as a product baseline; compare QI to classical R2I on identical candidates for algorithm evaluation.", "",
        "## Limitations and reproducibility", "",
        *[f"- {item}" for item in summary["limitations"]],
        "- Run `python benchmark_comparison.py` to regenerate the report, CSV records, and JSON summary. The script reads the local ignored `.streamlit/secrets.toml`; never commit that file.",
        "- Google Routes API requests may be billable under the configured Google Cloud project. This run is intentionally limited to the fixed six-trip set.", "",
        "## Artifacts", "", "- `benchmark_records.csv`: per method and trip raw metrics.", "- `benchmark_summary.json`: machine-readable aggregate and limitations.", "- `BENCHMARK_REPORT.md`: this report.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    report = run()
    print(f"Completed {report['successful_complete_trip_sets']} / {report['requested_trips']} trip sets")
    print("Artifacts: output/benchmark_comparison/BENCHMARK_REPORT.md")
