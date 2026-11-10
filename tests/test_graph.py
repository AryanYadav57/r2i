"""
tests/test_graph.py - Graph Subsystem Tests
Route-to-Impact (R2I) - Phase 2 Exit Gate

All tests here must PASS before Phase 3 begins.

Invariants:
  - Loaded graph has no self-loops
  - All edges have length attribute
  - All edges have highway attribute
  - Graph is strongly connected (largest SCC extracted)
  - Node attributes: node_degree, is_signal, highway_class_weight present
"""

import pytest
import networkx as nx
from r2i.graph.preprocessing import (
    remove_self_loops,
    impute_missing_attributes,
    extract_largest_component,
    validate_graph,
    clean_graph,
)
from r2i.graph.features import (
    compute_node_degrees,
    extract_signal_tags,
    map_highway_class_weights,
    get_highway_weight,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_graph():
    """Minimal synthetic MultiDiGraph for unit tests (no OSM download needed)."""
    G = nx.MultiDiGraph()
    G.add_node(1, highway="traffic_signals")
    G.add_node(2)
    G.add_node(3)
    G.add_edge(1, 2, 0, length=500.0, highway="primary",   travel_time=60.0, speed_kph=30.0)
    G.add_edge(2, 3, 0, length=300.0, highway="secondary", travel_time=40.0, speed_kph=30.0)
    G.add_edge(3, 1, 0, length=400.0, highway="tertiary",  travel_time=50.0, speed_kph=30.0)
    return G


@pytest.fixture
def dirty_graph():
    """Graph with self-loops and missing attributes for preprocessing tests."""
    G = nx.MultiDiGraph()
    G.add_node(10)
    G.add_node(20)
    G.add_node(30)
    # Normal edges
    G.add_edge(10, 20, 0, length=200.0, highway="primary", travel_time=24.0, speed_kph=30.0)
    G.add_edge(20, 30, 0, length=150.0, highway="secondary", travel_time=18.0, speed_kph=30.0)
    G.add_edge(30, 10, 0, length=100.0, travel_time=12.0, speed_kph=30.0)  # missing highway
    # Self-loop
    G.add_edge(10, 10, 0, length=0.0, highway="service")
    return G


@pytest.fixture
def disconnected_graph():
    """Graph with two weakly-connected components."""
    G = nx.MultiDiGraph()
    # Component A (3 nodes)
    G.add_node(1); G.add_node(2); G.add_node(3)
    G.add_edge(1, 2, 0, length=100.0, highway="primary", travel_time=12.0, speed_kph=30.0)
    G.add_edge(2, 3, 0, length=100.0, highway="primary", travel_time=12.0, speed_kph=30.0)
    G.add_edge(3, 1, 0, length=100.0, highway="primary", travel_time=12.0, speed_kph=30.0)
    # Component B (2 isolated nodes — no path to A)
    G.add_node(99); G.add_node(100)
    G.add_edge(99, 100, 0, length=50.0, highway="residential", travel_time=6.0, speed_kph=30.0)
    G.add_edge(100, 99, 0, length=50.0, highway="residential", travel_time=6.0, speed_kph=30.0)
    return G


# ---------------------------------------------------------------------------
# Preprocessing Tests
# ---------------------------------------------------------------------------

def test_no_self_loops(dirty_graph):
    """Graph must contain no self-loop edges after preprocessing."""
    G = remove_self_loops(dirty_graph)
    assert nx.number_of_selfloops(G) == 0


def test_remove_self_loops_preserves_other_edges(dirty_graph):
    """remove_self_loops must not delete non-self-loop edges."""
    edges_before = dirty_graph.number_of_edges() - nx.number_of_selfloops(dirty_graph)
    G = remove_self_loops(dirty_graph)
    assert G.number_of_edges() == edges_before


def test_all_edges_have_length(dirty_graph):
    """Every edge must have a length attribute after impute_missing_attributes."""
    G = remove_self_loops(dirty_graph)
    G = impute_missing_attributes(G)
    for u, v, key, data in G.edges(keys=True, data=True):
        assert "length" in data, f"Edge ({u},{v},{key}) missing length"
        assert data["length"] is not None


def test_all_edges_have_highway(dirty_graph):
    """Every edge must have a highway attribute after impute_missing_attributes."""
    G = remove_self_loops(dirty_graph)
    G = impute_missing_attributes(G)
    for u, v, key, data in G.edges(keys=True, data=True):
        assert "highway" in data, f"Edge ({u},{v},{key}) missing highway"
        assert data["highway"] is not None


def test_all_edges_have_travel_time(dirty_graph):
    """Every edge must have a computed travel_time after imputation."""
    G = remove_self_loops(dirty_graph)
    G = impute_missing_attributes(G)
    for u, v, key, data in G.edges(keys=True, data=True):
        assert "travel_time" in data
        assert data["travel_time"] >= 0.0


def test_extract_largest_component(disconnected_graph):
    """Largest SCC must contain 3 nodes (component A) not 2 (component B)."""
    G = extract_largest_component(disconnected_graph)
    assert G.number_of_nodes() == 3
    assert nx.is_strongly_connected(G)


def test_clean_graph_pipeline(dirty_graph):
    """clean_graph() must produce a graph that passes validate_graph()."""
    G = clean_graph(dirty_graph)
    assert validate_graph(G) is True


def test_validate_graph_catches_self_loops():
    """validate_graph() must raise AssertionError when self-loops are present."""
    G = nx.MultiDiGraph()
    G.add_node(1); G.add_node(2)
    G.add_edge(1, 2, 0, length=100.0, highway="primary", travel_time=12.0)
    G.add_edge(2, 1, 0, length=100.0, highway="primary", travel_time=12.0)
    G.add_edge(1, 1, 0, length=0.0, highway="service", travel_time=0.0)  # self-loop
    with pytest.raises(AssertionError, match="self-loop"):
        validate_graph(G)


# ---------------------------------------------------------------------------
# Feature Extraction Tests
# ---------------------------------------------------------------------------

def test_node_degree_attribute_set(synthetic_graph):
    """All nodes must have node_degree attribute after compute_node_degrees."""
    compute_node_degrees(synthetic_graph)
    for node in synthetic_graph.nodes():
        assert "node_degree" in synthetic_graph.nodes[node]
        assert isinstance(synthetic_graph.nodes[node]["node_degree"], int)


def test_node_degree_values_correct(synthetic_graph):
    """node_degree = number of distinct neighbouring nodes (physical streets)."""
    compute_node_degrees(synthetic_graph)
    U = synthetic_graph.to_undirected(as_view=True)
    for node in synthetic_graph.nodes():
        expected = len(set(U.neighbors(node)) - {node})
        assert synthetic_graph.nodes[node]["node_degree"] == expected


def test_is_signal_attribute_is_bool(synthetic_graph):
    """is_signal must be a boolean for all nodes."""
    extract_signal_tags(synthetic_graph)
    for node, data in synthetic_graph.nodes(data=True):
        assert isinstance(data.get("is_signal"), bool), \
            f"Node {node} has non-bool is_signal: {data.get('is_signal')}"


def test_traffic_signal_node_detected(synthetic_graph):
    """Node 1 has highway=traffic_signals and must be detected as a signal."""
    extract_signal_tags(synthetic_graph)
    assert synthetic_graph.nodes[1]["is_signal"] is True


def test_non_signal_nodes_are_false(synthetic_graph):
    """Nodes 2 and 3 have no highway tag and must not be detected as signals."""
    extract_signal_tags(synthetic_graph)
    assert synthetic_graph.nodes[2]["is_signal"] is False
    assert synthetic_graph.nodes[3]["is_signal"] is False


def test_highway_class_weight_in_range(synthetic_graph):
    """highway_class_weight must be in [0.0, 1.0] for all nodes."""
    map_highway_class_weights(synthetic_graph)
    for node, data in synthetic_graph.nodes(data=True):
        w = data.get("highway_class_weight", -1)
        assert 0.0 <= w <= 1.0, f"Node {node} has out-of-range weight: {w}"


def test_highway_class_weight_primary_is_max(synthetic_graph):
    """Node adjacent to primary road must get weight = 1.0 (highest tier)."""
    map_highway_class_weights(synthetic_graph)
    # Node 1 is adjacent to a primary road (edge 1->2)
    assert synthetic_graph.nodes[1]["highway_class_weight"] == 1.0


def test_get_highway_weight_known_type():
    """get_highway_weight must return correct value for known highway types."""
    from r2i import config
    assert get_highway_weight("primary") == config.HIGHWAY_CLASS_WEIGHTS["primary"]
    assert get_highway_weight("residential") == config.HIGHWAY_CLASS_WEIGHTS["residential"]


def test_get_highway_weight_unknown_type():
    """get_highway_weight must return DEFAULT for unknown highway types."""
    from r2i import config
    assert get_highway_weight("xyz_unknown") == config.HIGHWAY_CLASS_DEFAULT


def test_extract_all_features_sets_all_attrs(synthetic_graph):
    """extract_all_features must set all three required attributes on every node."""
    from r2i.graph.features import extract_all_features
    extract_all_features(synthetic_graph)
    required = {"node_degree", "is_signal", "highway_class_weight"}
    for node, data in synthetic_graph.nodes(data=True):
        missing = required - set(data.keys())
        assert not missing, f"Node {node} missing attributes: {missing}"
