"""
tests/test_routing.py - Routing Engine Tests
Route-to-Impact (R2I) - Phase 3 & Phase 7 Exit Gate

Phase 3 tests:  ALL active (baseline router)
Phase 7 tests:  ALL active (eco-router -- implemented in Phase 7)

Key Invariants:
  - Baseline returns deterministic results for same OD pair
  - Baseline picks shortest distance route (not eco-optimised)
  - origin==dest returns single-node path with zero metrics
  - Disconnected pair raises RouteNotFoundError
  - Eco-router diverges from baseline on congested corridor
"""

import math
import time

import pytest
import networkx as nx

from r2i import config
from r2i.routing.baseline import (
    shortest_path,
    compute_path_metrics,
    total_edge_length,
    total_travel_time,
    count_intersections,
    RouteNotFoundError,
)
from r2i.routing.router import (
    eco_route,
    compare_routes,
    compute_eco_metrics,
)
from r2i.models.vehicle import ICEVehicle, EVVehicle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_graph():
    """
    Graph layout:
      1 --100m--> 2 --100m--> 3   (via node 2, total 200m)
      1 --210m-----------> 3      (direct, total 210m)

    Baseline (distance-optimal) must choose: 1 -> 2 -> 3 (200m).
    Node 2 is a high-congestion node (signal, degree 8, primary road).
    The eco-router (Phase 7) should prefer 1 -> 3 to avoid node 2 idle cost.
    """
    G = nx.MultiDiGraph()
    G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(2, node_degree=8, is_signal=True,  highway_class_weight=1.0)
    G.add_node(3, node_degree=1, is_signal=False, highway_class_weight=0.2)

    G.add_edge(1, 2, 0, length=100.0, highway="primary",     travel_time=12.0, speed_kph=30.0)
    G.add_edge(2, 3, 0, length=100.0, highway="primary",     travel_time=12.0, speed_kph=30.0)
    G.add_edge(1, 3, 0, length=210.0, highway="residential", travel_time=25.2, speed_kph=30.0)
    return G


@pytest.fixture
def linear_graph():
    """Straight-line: 1->2->3->4. Only one possible path. Edges: 100m/12s, 150m/18s, 200m/24s."""
    G = nx.MultiDiGraph()
    for nid in [1, 2, 3, 4]:
        G.add_node(nid, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_edge(1, 2, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="residential")
    G.add_edge(2, 3, 0, length=150.0, travel_time=18.0, speed_kph=30.0, highway="residential")
    G.add_edge(3, 4, 0, length=200.0, travel_time=24.0, speed_kph=30.0, highway="residential")
    return G


@pytest.fixture
def disconnected_graph():
    """Two isolated components: {10,11} and {20,21}. No path between them."""
    G = nx.MultiDiGraph()
    G.add_node(10, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_node(11, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_node(20, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_node(21, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_edge(10, 11, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="residential")
    G.add_edge(20, 21, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="residential")
    return G


@pytest.fixture
def multi_edge_graph():
    """Parallel edges between nodes 1 and 2: lengths 100m and 300m."""
    G = nx.MultiDiGraph()
    for nid in [1, 2, 3]:
        G.add_node(nid, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_edge(1, 2, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="primary")
    G.add_edge(1, 2, 1, length=300.0, travel_time=36.0, speed_kph=30.0, highway="secondary")
    G.add_edge(2, 3, 0, length=200.0, travel_time=24.0, speed_kph=30.0, highway="residential")
    return G


@pytest.fixture
def intersection_graph():
    """Path: 1->5->6->2. Expected intersections: 1 (only node 5)."""
    G = nx.MultiDiGraph()
    G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(5, node_degree=4, is_signal=True,  highway_class_weight=1.0)
    G.add_node(6, node_degree=2, is_signal=False, highway_class_weight=0.3)
    G.add_node(2, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(7, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_node(8, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_edge(1, 5, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="primary")
    G.add_edge(5, 6, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="secondary")
    G.add_edge(6, 2, 0, length=100.0, travel_time=12.0, speed_kph=30.0, highway="secondary")
    G.add_edge(7, 5, 0, length=50.0,  travel_time=6.0,  speed_kph=30.0, highway="tertiary")
    G.add_edge(8, 5, 0, length=50.0,  travel_time=6.0,  speed_kph=30.0, highway="tertiary")
    return G


# ---------------------------------------------------------------------------
# Phase 3 Tests: Baseline Router
# ---------------------------------------------------------------------------

class TestShortestPath:

    def test_returns_tuple(self, simple_graph):
        result = shortest_path(simple_graph, 1, 3)
        assert isinstance(result, tuple) and len(result) == 2
        path, metrics = result
        assert isinstance(path, list) and isinstance(metrics, dict)

    def test_baseline_picks_shortest_distance(self, simple_graph):
        path, _ = shortest_path(simple_graph, 1, 3)
        assert path == [1, 2, 3], f"Expected [1,2,3] but got {path}"

    def test_deterministic(self, simple_graph):
        path1, metrics1 = shortest_path(simple_graph, 1, 3)
        path2, metrics2 = shortest_path(simple_graph, 1, 3)
        assert path1 == path2
        assert metrics1 == metrics2

    def test_returns_required_metric_keys(self, simple_graph):
        _, metrics = shortest_path(simple_graph, 1, 3)
        required = {"distance_km", "travel_time_min", "node_count", "intersection_count"}
        assert not (required - set(metrics.keys()))

    def test_distance_correct(self, linear_graph):
        _, metrics = shortest_path(linear_graph, 1, 4)
        assert abs(metrics["distance_km"] - 0.45) < 1e-6

    def test_travel_time_correct(self, linear_graph):
        _, metrics = shortest_path(linear_graph, 1, 4)
        assert abs(metrics["travel_time_min"] - 0.9) < 1e-6

    def test_node_count_correct(self, linear_graph):
        _, metrics = shortest_path(linear_graph, 1, 4)
        assert metrics["node_count"] == 4

    def test_origin_equals_destination(self, simple_graph):
        path, metrics = shortest_path(simple_graph, 1, 1)
        assert path == [1]
        assert metrics["distance_km"] == 0.0
        assert metrics["node_count"] == 1

    def test_disconnected_raises_route_not_found(self, disconnected_graph):
        with pytest.raises(RouteNotFoundError):
            shortest_path(disconnected_graph, 10, 20)

    def test_multi_edge_picks_minimum_length(self, multi_edge_graph):
        _, metrics = shortest_path(multi_edge_graph, 1, 3)
        assert abs(metrics["distance_km"] - 0.3) < 1e-6


class TestPathHelpers:

    def test_total_edge_length(self, linear_graph):
        assert abs(total_edge_length(linear_graph, [1, 2, 3, 4]) - 450.0) < 1e-6

    def test_total_travel_time(self, linear_graph):
        assert abs(total_travel_time(linear_graph, [1, 2, 3, 4]) - 54.0) < 1e-6

    def test_count_intersections_correct(self, intersection_graph):
        assert count_intersections(intersection_graph, [1, 5, 6, 2]) == 1

    def test_count_intersections_empty_interior(self, simple_graph):
        assert count_intersections(simple_graph, [1, 3]) == 0

    def test_compute_path_metrics_single_node(self):
        G = nx.MultiDiGraph()
        G.add_node(99)
        m = compute_path_metrics(G, [99])
        assert m["distance_km"] == 0.0 and m["node_count"] == 1


# ---------------------------------------------------------------------------
# Phase 7 Tests: Eco-Router
# ---------------------------------------------------------------------------

class TestEcoRoute:

    def test_returns_tuple(self, simple_graph):
        result = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], list) and isinstance(result[1], dict)

    def test_path_starts_at_origin(self, simple_graph):
        path, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        assert path[0] == 1

    def test_path_ends_at_destination(self, simple_graph):
        path, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        assert path[-1] == 3

    def test_all_path_nodes_in_graph(self, simple_graph):
        path, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        graph_nodes = set(simple_graph.nodes())
        for node in path:
            assert node in graph_nodes

    def test_path_is_connected(self, simple_graph):
        path, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        for u, v in zip(path[:-1], path[1:]):
            assert simple_graph.has_edge(u, v)

    def test_returns_required_metric_keys(self, simple_graph):
        _, metrics = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        required = {
            "distance_km", "travel_time_s", "travel_time_min",
            "total_idle_s", "total_co2_g", "fuel_ml", "node_count"
        }
        assert not (required - set(metrics.keys()))

    def test_metrics_are_finite(self, simple_graph):
        _, metrics = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        for key, val in metrics.items():
            assert math.isfinite(val), f"Metric {key!r} not finite: {val}"

    def test_metrics_are_non_negative(self, simple_graph):
        _, metrics = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        for key, val in metrics.items():
            assert val >= 0.0, f"Metric {key!r} is negative: {val}"

    def test_origin_equals_destination(self, simple_graph):
        path, metrics = eco_route(simple_graph, 1, 1, ICEVehicle(), config)
        assert path == [1]
        assert metrics["distance_km"] == 0.0
        assert metrics["node_count"] == 1

    def test_disconnected_raises_route_not_found(self, disconnected_graph):
        with pytest.raises(RouteNotFoundError):
            eco_route(disconnected_graph, 10, 20, ICEVehicle(), config)

    def test_deterministic(self, simple_graph):
        path1, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        path2, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        assert path1 == path2

    def test_ev_fuel_ml_always_zero(self, simple_graph):
        _, metrics = eco_route(simple_graph, 1, 3, EVVehicle(), config)
        assert metrics["fuel_ml"] == 0.0

    def test_eco_route_diverges_on_congested_corridor(self, simple_graph):
        """R2I must choose the direct residential route over the congested primary corridor."""
        baseline_path, _ = shortest_path(simple_graph, 1, 3)
        eco_path, _ = eco_route(simple_graph, 1, 3, ICEVehicle(), config)
        assert baseline_path == [1, 2, 3], "Baseline fixture broken"
        assert eco_path == [1, 3], \
            f"ICE eco-route should avoid congested node 2; got {eco_path}"


class TestComputeEcoMetrics:

    def test_single_node_path_returns_zeros(self, simple_graph):
        metrics = compute_eco_metrics(simple_graph, [1], ICEVehicle())
        assert metrics["distance_km"] == 0.0
        assert metrics["node_count"] == 1

    def test_metrics_non_negative(self, linear_graph):
        from r2i.routing.cost import apply_weights_to_graph
        apply_weights_to_graph(linear_graph, ICEVehicle(), config)
        metrics = compute_eco_metrics(linear_graph, [1, 2, 3, 4], ICEVehicle())
        for k, v in metrics.items():
            assert v >= 0.0, f"Metric {k!r} negative: {v}"

    def test_distance_matches_edge_sum(self, linear_graph):
        from r2i.routing.cost import apply_weights_to_graph
        apply_weights_to_graph(linear_graph, ICEVehicle(), config)
        metrics = compute_eco_metrics(linear_graph, [1, 2, 3, 4], ICEVehicle())
        assert abs(metrics["distance_km"] - 0.45) < 1e-6

    def test_ev_fuel_zero(self, simple_graph):
        from r2i.routing.cost import apply_weights_to_graph
        apply_weights_to_graph(simple_graph, EVVehicle(), config)
        metrics = compute_eco_metrics(simple_graph, [1, 3], EVVehicle())
        assert metrics["fuel_ml"] == 0.0


class TestCompareRoutes:

    def test_returns_dict(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert isinstance(result, dict)

    def test_returns_required_keys(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        required = {
            "baseline_path", "r2i_path", "baseline", "r2i",
            "diverged", "avoided_nodes", "delta"
        }
        assert not (required - set(result.keys()))

    def test_diverged_is_bool(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert isinstance(result["diverged"], bool)

    def test_diverges_on_congested_graph(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert result["diverged"] is True, \
            f"Expected divergence; baseline={result['baseline_path']} r2i={result['r2i_path']}"

    def test_same_origin_dest_no_crash(self, simple_graph):
        result = compare_routes(simple_graph, 1, 1, ICEVehicle(), config)
        assert result["diverged"] is False
        assert result["baseline_path"] == [1]
        assert result["r2i_path"] == [1]

    def test_delta_keys_present(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        required_delta = {
            "distance_km", "travel_time_s", "total_idle_s", "total_co2_g", "fuel_ml"
        }
        assert not (required_delta - set(result["delta"].keys()))

    def test_delta_values_are_finite(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        for k, v in result["delta"].items():
            assert math.isfinite(v), f"Delta {k!r} not finite: {v}"

    def test_avoided_nodes_is_list(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert isinstance(result["avoided_nodes"], list)

    def test_avoided_nodes_not_in_r2i_path(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        r2i_set = set(result["r2i_path"])
        for node in result["avoided_nodes"]:
            assert node not in r2i_set

    def test_baseline_path_endpoints(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert result["baseline_path"][0] == 1
        assert result["baseline_path"][-1] == 3

    def test_r2i_path_endpoints(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert result["r2i_path"][0] == 1
        assert result["r2i_path"][-1] == 3

    def test_compare_disconnected_raises(self, disconnected_graph):
        with pytest.raises(RouteNotFoundError):
            compare_routes(disconnected_graph, 10, 20, ICEVehicle(), config)

    def test_r2i_lower_or_equal_idle_than_baseline(self, simple_graph):
        result = compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        assert result["r2i"]["total_idle_s"] <= result["baseline"]["total_idle_s"], \
            "Eco-route should have less or equal idling than baseline"

    def test_performance_under_two_seconds(self, simple_graph):
        start = time.perf_counter()
        compare_routes(simple_graph, 1, 3, ICEVehicle(), config)
        elapsed = time.perf_counter() - start
        assert elapsed < config.PERF_TARGET_SECONDS, \
            f"compare_routes took {elapsed:.2f}s, target={config.PERF_TARGET_SECONDS}s"
