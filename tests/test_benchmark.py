"""
tests/test_benchmark.py — Benchmark Tests
Route-to-Impact (R2I) · Phase 9 Supporting Tests
"""

import pytest
import networkx as nx
import pandas as pd
import tempfile
import os

from r2i import config
from r2i.models.vehicle import ICEVehicle
from r2i.evaluation.benchmark import run_monte_carlo, save_benchmark_results, load_benchmark_results

@pytest.fixture
def mock_graph():
    """Simple graph that allows some routing but will raise RouteNotFoundError for disconnected nodes."""
    G = nx.MultiDiGraph()
    G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(2, node_degree=4, is_signal=True,  highway_class_weight=1.0)
    G.add_node(3, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(4, node_degree=1, is_signal=False, highway_class_weight=0.2)
    # Connected component
    G.add_edge(1, 2, 0, length=200.0, highway="primary",     travel_time=24.0, speed_kph=30.0)
    G.add_edge(2, 3, 0, length=200.0, highway="primary",     travel_time=24.0, speed_kph=30.0)
    G.add_edge(1, 3, 0, length=500.0, highway="residential", travel_time=60.0, speed_kph=30.0)
    # Disconnected node
    G.add_node(5, node_degree=1, is_signal=False, highway_class_weight=0.2)

    # Needs to be a valid graph to apply weights
    from r2i.routing.cost import apply_weights_to_graph
    apply_weights_to_graph(G, ICEVehicle(), config)

    return G

def test_run_monte_carlo_returns_dataframe(mock_graph):
    df = run_monte_carlo(mock_graph, ICEVehicle(), n_trips=10, seed=42)
    assert isinstance(df, pd.DataFrame)

    required_cols = [
        "origin", "dest", "baseline_dist_km", "r2i_dist_km", "baseline_time_s", "r2i_time_s",
        "baseline_idle_s", "r2i_idle_s", "fuel_saved_ml", "co2_avoided_g", "time_delta_s", "diverged"
    ]
    for col in required_cols:
        assert col in df.columns

def test_run_monte_carlo_skips_errors(mock_graph):
    # n_trips=50 with 4 nodes means we will definitely hit node 5 (disconnected)
    # or origin == dest. The function should not crash.
    df = run_monte_carlo(mock_graph, ICEVehicle(), n_trips=50, seed=42)
    # We should have some successful routes
    assert len(df) > 0

def test_save_and_load_benchmark_results(mock_graph):
    df = pd.DataFrame([{"origin": 1, "dest": 3, "diverged": True}])
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.csv")
        save_benchmark_results(df, path)
        assert os.path.exists(path)

        df_loaded = load_benchmark_results(path)
        assert len(df_loaded) == len(df)
        assert list(df_loaded.columns) == list(df.columns)
