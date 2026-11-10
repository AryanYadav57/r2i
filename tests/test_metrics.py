"""
tests/test_metrics.py — Evaluation Metrics Tests
Route-to-Impact (R2I) · Phase 9 Supporting Tests

Validates trip metric computation and aggregation helpers.
"""


def test_trip_delta_fuel_saved_positive_when_r2i_avoids_idle():
    """Fuel saved must be positive when R2I has less idle time than baseline."""
    from r2i.evaluation.metrics import compute_trip_delta
    baseline = {"total_idle_s": 60.0, "fuel_ml": 10.0, "distance_km": 3.0}
    r2i      = {"total_idle_s": 20.0, "fuel_ml": 2.0, "distance_km": 3.5}
    delta = compute_trip_delta(baseline, r2i)

    assert delta is not None
    assert delta.get("fuel_saved_ml", 0) > 0
    assert delta["fuel_saved_ml"] == 8.0
    assert delta["idle_saved_s"] == 40.0


def test_aggregate_computes_divergence_rate():
    """Aggregated results must include divergence_rate field."""
    from r2i.evaluation.metrics import aggregate_benchmark_results
    mock_results = [{"diverged": True}, {"diverged": False}, {"diverged": True}]
    summary = aggregate_benchmark_results(mock_results)

    assert "divergence_rate" in summary
    assert round(summary["divergence_rate"], 2) == 66.67
    assert summary["total_trips"] == 3

def test_aggregate_empty_list_returns_empty_dict():
    from r2i.evaluation.metrics import aggregate_benchmark_results
    assert aggregate_benchmark_results([]) == {}

def test_results_to_dataframe():
    from r2i.evaluation.metrics import results_to_dataframe
    import pandas as pd

    mock_results = [
        {
            "baseline_path": [1, 2, 3],
            "r2i_path": [1, 4, 3],
            "diverged": True,
            "baseline": {"distance_km": 1.0, "travel_time_s": 100.0, "total_idle_s": 10.0},
            "r2i": {"distance_km": 1.2, "travel_time_s": 120.0, "total_idle_s": 5.0},
            "delta": {"fuel_ml": -2.5, "total_co2_g": -10.0, "travel_time_s": 20.0}
        }
    ]
    df = results_to_dataframe(mock_results)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]

    assert row["origin"] == 1
    assert row["dest"] == 3
    assert row["baseline_dist_km"] == 1.0
    assert row["r2i_dist_km"] == 1.2
    assert row["fuel_saved_ml"] == 2.5
    assert row["co2_avoided_g"] == 10.0
    assert row["time_delta_s"] == 20.0
    assert row["diverged"] == True

