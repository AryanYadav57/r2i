"""
evaluation/metrics.py — Trip Metric Computation Helpers
Route-to-Impact (R2I) · Phase 9 Supporting Module

Provides helper functions to compute, aggregate, and format trip-level
metrics from route comparison results.
"""

from typing import List
import pandas as pd


def compute_trip_delta(baseline_metrics: dict, r2i_metrics: dict) -> dict:
    """
    Compute per-metric deltas between baseline and R2I routes.

    Delta convention: positive value = R2I is worse (more distance/time);
    negative idle/fuel/co2 delta = R2I saves that resource.

    Args:
        baseline_metrics: Metric dict from baseline router.
        r2i_metrics:      Metric dict from eco-router.

    Returns:
        dict of delta values keyed by metric name.
    """
    keys = ["distance_km", "travel_time_s", "travel_time_min", "total_idle_s", "total_co2_g", "fuel_ml"]
    delta = {}
    for k in keys:
        if k in baseline_metrics and k in r2i_metrics:
            delta[k] = r2i_metrics[k] - baseline_metrics[k]
    # For compatibility with test cases that expect 'fuel_saved_ml':
    if "fuel_ml" not in delta and "fuel_saved_ml" in r2i_metrics:
        pass # mock tests sometimes have these
    elif "fuel_saved_ml" not in r2i_metrics:
        # Some mock tests pass fuel_saved_ml directly. Let's just calculate it.
        delta["fuel_saved_ml"] = baseline_metrics.get("fuel_ml", 0) - r2i_metrics.get("fuel_ml", 0)

    # Also support mock tests that pass total_idle_s explicitly
    if "total_idle_s" in baseline_metrics and "total_idle_s" in r2i_metrics:
        delta["idle_saved_s"] = baseline_metrics["total_idle_s"] - r2i_metrics["total_idle_s"]

    return delta


def aggregate_benchmark_results(results: List[dict]) -> dict:
    """
    Compute summary statistics over a list of trip comparison dicts.

    Args:
        results: List of compare_routes() output dicts.

    Returns:
        dict with mean, median, std for each metric;
        plus divergence_rate (% of trips where routes differed).
    """
    if not results:
        return {}

    diverged_count = sum(1 for r in results if r.get("diverged", False))
    summary = {
        "divergence_rate": (diverged_count / len(results)) * 100.0,
        "total_trips": len(results),
    }

    # Extract deltas if present
    deltas = []
    for r in results:
        if "delta" in r:
            deltas.append(r["delta"])
        else:
            # Maybe it's a mock that just has 'diverged'
            pass

    if deltas:
        df_deltas = pd.DataFrame(deltas)
        for col in df_deltas.columns:
            summary[f"{col}_mean"] = df_deltas[col].mean()
            summary[f"{col}_median"] = df_deltas[col].median()
            summary[f"{col}_std"] = df_deltas[col].std()

    return summary


def results_to_dataframe(results: List[dict]) -> pd.DataFrame:
    """
    Convert a list of trip comparison dicts to a flat pandas DataFrame
    for CSV export and analysis.

    Output CSV columns:
      origin, dest, baseline_dist_km, r2i_dist_km, baseline_time_s, r2i_time_s,
      baseline_idle_s, r2i_idle_s, fuel_saved_ml, co2_avoided_g, time_delta_s, diverged
    """
    rows = []
    for r in results:
        base = r.get("baseline", {})
        r2i = r.get("r2i", {})
        delta = r.get("delta", {})

        # Determine origin and dest from paths if available
        origin = r["baseline_path"][0] if "baseline_path" in r and r["baseline_path"] else None
        dest = r["baseline_path"][-1] if "baseline_path" in r and r["baseline_path"] else None

        row = {
            "origin": origin,
            "dest": dest,
            "baseline_dist_km": base.get("distance_km", 0.0),
            "r2i_dist_km": r2i.get("distance_km", 0.0),
            "baseline_time_s": base.get("travel_time_s", 0.0),
            "r2i_time_s": r2i.get("travel_time_s", 0.0),
            "baseline_idle_s": base.get("total_idle_s", 0.0),
            "r2i_idle_s": r2i.get("total_idle_s", 0.0),
            "fuel_saved_ml": -delta.get("fuel_ml", 0.0),      # positive means saved
            "co2_avoided_g": -delta.get("total_co2_g", 0.0),  # positive means saved
            "time_delta_s": delta.get("travel_time_s", 0.0),  # positive means r2i took longer
            "diverged": r.get("diverged", False),
        }
        rows.append(row)

    return pd.DataFrame(rows)
