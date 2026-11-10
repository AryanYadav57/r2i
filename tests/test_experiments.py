"""
tests/test_experiments.py — Phase 10 Sensitivity Analysis Tests
Route-to-Impact (R2I)
"""

import pytest
import networkx as nx
import pandas as pd

from r2i import config
from r2i.models.vehicle import ICEVehicle
from r2i.evaluation.experiments import sweep_t_base_idle, sweep_alpha

@pytest.fixture
def mock_graph():
    """Simple graph for testing sensitivity sweeps."""
    G = nx.MultiDiGraph()
    G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(2, node_degree=4, is_signal=True,  highway_class_weight=1.0)
    G.add_node(3, node_degree=2, is_signal=False, highway_class_weight=0.2)

    G.add_edge(1, 2, 0, length=200.0, highway="primary",     travel_time=24.0, speed_kph=30.0)
    G.add_edge(2, 3, 0, length=200.0, highway="primary",     travel_time=24.0, speed_kph=30.0)
    G.add_edge(1, 3, 0, length=500.0, highway="residential", travel_time=60.0, speed_kph=30.0)

    from r2i.routing.cost import apply_weights_to_graph
    apply_weights_to_graph(G, ICEVehicle(), config)
    return G

def test_sweep_t_base_idle(mock_graph):
    df = sweep_t_base_idle(mock_graph, ICEVehicle(), values=[10.0, 20.0], n_trips=2)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df["t_base_idle"]) == [10.0, 20.0]
    assert "mean_fuel_saved" in df.columns
    assert "mean_co2_avoided" in df.columns
    assert "mean_time_delta" in df.columns
    assert "divergence_rate" in df.columns

def test_sweep_alpha(mock_graph):
    df = sweep_alpha(mock_graph, ICEVehicle(), values=[0.0, 1.0], n_trips=2)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df["alpha"]) == [0.0, 1.0]
    assert "divergence_rate" in df.columns
    assert "mean_time_delta" in df.columns
    assert "mean_fuel_saved" in df.columns

