"""
tests/test_congestion.py - Congestion Model Unit Tests
Route-to-Impact (R2I) - Phase 4 Exit Gate

All tests here must PASS (100% rate) before Phase 5 begins.

Key Invariants:
  - Congestion score S(v) always in [0.0, 1.0]
  - Boundary conditions: degree=0, degree=max, signal=True/False
  - Higher degree node -> equal or higher congestion score (monotonic)
  - Traffic signal node -> strictly higher score than identical non-signal
  - T_idle is exactly proportional to S(v) * T_BASE_IDLE
  - apply_congestion_to_graph attaches both attributes to every node
"""

import math
import pytest
import networkx as nx

from r2i import config
from r2i.graph.features import get_highway_weight
from r2i.models.congestion import (
    compute_congestion_score,
    compute_idle_time,
    apply_congestion_to_graph,
    MAX_DEGREE_NORMALISE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(degree: int, is_signal: bool, highway_class: str) -> dict:
    """Construct a minimal node_data dict for testing."""
    return {
        "node_degree":          degree,
        "is_signal":            is_signal,
        "highway_class_weight": get_highway_weight(highway_class),
    }


def make_graph_with_nodes(*node_specs) -> nx.MultiDiGraph:
    """
    Build a minimal connected MultiDiGraph.
    node_specs: list of (degree, is_signal, highway_class) tuples.
    Nodes are connected in a ring so the graph is strongly connected.
    """
    G = nx.MultiDiGraph()
    nodes = []
    for i, (deg, sig, road) in enumerate(node_specs, start=1):
        G.add_node(i,
                   node_degree=deg,
                   is_signal=sig,
                   highway_class_weight=get_highway_weight(road))
        nodes.append(i)

    # Ring connectivity so apply_congestion_to_graph has a valid graph
    for i in range(len(nodes)):
        u = nodes[i]
        v = nodes[(i + 1) % len(nodes)]
        G.add_edge(u, v, 0, length=100.0, travel_time=12.0,
                   speed_kph=30.0, highway="secondary")
    return G


# ---------------------------------------------------------------------------
# Phase 4 Tests: Congestion Score Bounds & Invariants
# ---------------------------------------------------------------------------

class TestCongestionScoreBounds:

    @pytest.mark.parametrize("degree,signal,road", [
        (0,  False, "residential"),   # Minimum case
        (1,  False, "tertiary"),
        (2,  False, "secondary"),
        (4,  False, "secondary"),
        (4,  True,  "primary"),       # Busy signalised junction
        (8,  True,  "primary"),       # Max degree saturates model
        (12, True,  "primary"),       # Extreme — must clip to 1.0
        (0,  True,  "motorway"),      # Signal on motorway (unusual but valid)
        (6,  False, "residential"),   # High-degree residential
    ])
    def test_score_always_in_unit_interval(self, degree, signal, road):
        """S(v) must always be in [0.0, 1.0] regardless of inputs."""
        score = compute_congestion_score(make_node(degree, signal, road), config)
        assert 0.0 <= score <= 1.0, \
            f"Score {score:.4f} out of [0,1]  degree={degree} signal={signal} road={road}"

    def test_score_is_finite(self):
        """Score must never be NaN or infinite."""
        for degree in [0, 1, 4, 8, 100]:
            for sig in [True, False]:
                score = compute_congestion_score(
                    make_node(degree, sig, "primary"), config
                )
                assert math.isfinite(score), \
                    f"Non-finite score {score} for degree={degree} signal={sig}"

    def test_minimum_node_score_non_negative(self):
        """degree=0, no signal, lowest-weight road must produce score >= 0."""
        score = compute_congestion_score(make_node(0, False, "service"), config)
        assert score >= 0.0

    def test_extreme_degree_clips_to_one(self):
        """A degree far exceeding MAX_DEGREE_NORMALISE must produce score = 1.0."""
        score = compute_congestion_score(make_node(999, True, "primary"), config)
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_perfect_node_score_is_one(self):
        """MAX_DEGREE_NORMALISE + signal + primary road must saturate to 1.0."""
        score = compute_congestion_score(
            make_node(MAX_DEGREE_NORMALISE, True, "primary"), config
        )
        assert score == 1.0, f"Expected 1.0 for saturated node, got {score}"

    def test_zero_node_score_possible(self):
        """degree=0, no signal, minimal road weight must produce score close to 0."""
        score = compute_congestion_score(make_node(0, False, "motorway"), config)
        # motorway = 0.1 weight, so score = (0*0.5 + 0*0.3 + 0.1*0.2) / 4.5 = 0.02/4.5
        assert score < 0.1, f"Expected low score for minimal node, got {score}"


class TestCongestionScoreMonotonicity:

    def test_signal_strictly_increases_score(self):
        """is_signal=True must produce a STRICTLY higher score than is_signal=False."""
        no_sig  = compute_congestion_score(make_node(3, False, "secondary"), config)
        with_sig = compute_congestion_score(make_node(3, True,  "secondary"), config)
        assert with_sig > no_sig, \
            f"Signal should increase score: with={with_sig:.4f} <= no={no_sig:.4f}"

    @pytest.mark.parametrize("degree_low,degree_high,road", [
        (0, 2,  "residential"),
        (1, 4,  "secondary"),
        (2, 6,  "primary"),
        (4, 8,  "primary"),
    ])
    def test_higher_degree_nondecreasing_score(self, degree_low, degree_high, road):
        """Higher node degree must produce >= score (monotonicity in degree)."""
        score_low  = compute_congestion_score(make_node(degree_low,  False, road), config)
        score_high = compute_congestion_score(make_node(degree_high, False, road), config)
        assert score_high >= score_low, \
            f"Monotonicity violated: degree {degree_low}->{degree_high}  " \
            f"{score_low:.4f}->{score_high:.4f}"

    def test_primary_higher_than_residential_same_degree(self):
        """Primary road must produce a higher score than residential (same degree, no signal)."""
        score_res  = compute_congestion_score(make_node(3, False, "residential"), config)
        score_prim = compute_congestion_score(make_node(3, False, "primary"),     config)
        assert score_prim > score_res, \
            f"Primary should score higher than residential: {score_prim:.4f} <= {score_res:.4f}"


class TestCongestionScoreArithmetic:

    def test_score_formula_matches_manual_calculation(self):
        """
        Manually verify the formula for a specific node.
        Node: degree=4, signal=True, highway=primary (weight=1.0)

        w_d=0.5, w_s=0.3, w_c=0.2
        max_possible = 8*0.5 + 1*0.3 + 1*0.2 = 4.5
        raw = 4*0.5 + 1*0.3 + 1.0*0.2 = 2.0 + 0.3 + 0.2 = 2.5
        score = 2.5 / 4.5 = 0.5555...
        """
        node = make_node(degree=4, is_signal=True, highway_class="primary")
        score = compute_congestion_score(node, config)
        expected = (
            (4 * config.DEGREE_WEIGHT) +
            (1 * config.SIGNAL_WEIGHT) +
            (config.HIGHWAY_CLASS_WEIGHTS["primary"] * config.ROAD_CLASS_WEIGHT)
        ) / (MAX_DEGREE_NORMALISE * config.DEGREE_WEIGHT + config.SIGNAL_WEIGHT + config.ROAD_CLASS_WEIGHT)
        assert abs(score - expected) < 1e-9, f"Expected {expected:.6f}, got {score:.6f}"

    def test_no_signal_formula_matches_manual(self):
        """
        Manually verify: degree=2, signal=False, highway=tertiary (weight=0.5)
        raw = 2*0.5 + 0*0.3 + 0.5*0.2 = 1.0 + 0.0 + 0.1 = 1.1
        score = 1.1 / 4.5 = 0.2444...
        """
        node = make_node(degree=2, is_signal=False, highway_class="tertiary")
        score = compute_congestion_score(node, config)
        expected = (
            2 * config.DEGREE_WEIGHT +
            0 * config.SIGNAL_WEIGHT +
            config.HIGHWAY_CLASS_WEIGHTS["tertiary"] * config.ROAD_CLASS_WEIGHT
        ) / (MAX_DEGREE_NORMALISE * config.DEGREE_WEIGHT + config.SIGNAL_WEIGHT + config.ROAD_CLASS_WEIGHT)
        assert abs(score - expected) < 1e-9, f"Expected {expected:.6f}, got {score:.6f}"

    def test_missing_node_degree_defaults_to_zero(self):
        """If node_degree is missing, must not raise - defaults to 0."""
        node = {"is_signal": False, "highway_class_weight": 0.3}
        score = compute_congestion_score(node, config)
        assert 0.0 <= score <= 1.0

    def test_missing_is_signal_defaults_to_false(self):
        """If is_signal is missing, must not raise - defaults to False."""
        node = {"node_degree": 4, "highway_class_weight": 0.7}
        score = compute_congestion_score(node, config)
        assert 0.0 <= score <= 1.0

    def test_missing_highway_weight_uses_default(self):
        """If highway_class_weight is missing, must use HIGHWAY_CLASS_DEFAULT."""
        node = {"node_degree": 3, "is_signal": False}
        score = compute_congestion_score(node, config)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Phase 4 Tests: Idle Time
# ---------------------------------------------------------------------------

class TestIdleTime:

    def test_idle_time_exactly_proportional(self):
        """T_idle must be exactly score * T_BASE_IDLE (no rounding errors)."""
        node  = make_node(degree=4, is_signal=True, highway_class="primary")
        score = compute_congestion_score(node, config)
        idle  = compute_idle_time(score, config)
        assert abs(idle - score * config.T_BASE_IDLE) < 1e-9

    def test_idle_time_zero_score(self):
        """Zero congestion score must produce zero idle time."""
        assert compute_idle_time(0.0, config) == 0.0

    def test_idle_time_max_score(self):
        """Score=1.0 must produce exactly T_BASE_IDLE seconds of idle."""
        assert abs(compute_idle_time(1.0, config) - config.T_BASE_IDLE) < 1e-9

    def test_idle_time_half_score(self):
        """Score=0.5 must produce exactly T_BASE_IDLE/2 seconds."""
        assert abs(compute_idle_time(0.5, config) - config.T_BASE_IDLE / 2) < 1e-9

    def test_idle_time_non_negative_for_all_scores(self):
        """Idle time must be >= 0 for any score in [0,1]."""
        for score in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            assert compute_idle_time(score, config) >= 0.0


# ---------------------------------------------------------------------------
# Phase 4 Tests: Graph-level Application
# ---------------------------------------------------------------------------

class TestApplyCongestionToGraph:

    def test_all_nodes_get_congestion_score(self):
        """Every node must have congestion_score after apply_congestion_to_graph."""
        G = make_graph_with_nodes(
            (2, False, "secondary"),
            (4, True,  "primary"),
            (1, False, "residential"),
        )
        apply_congestion_to_graph(G, config)
        for node, data in G.nodes(data=True):
            assert "congestion_score" in data, f"Node {node} missing congestion_score"

    def test_all_nodes_get_idle_time(self):
        """Every node must have idle_time_s after apply_congestion_to_graph."""
        G = make_graph_with_nodes(
            (2, False, "secondary"),
            (4, True,  "primary"),
        )
        apply_congestion_to_graph(G, config)
        for node, data in G.nodes(data=True):
            assert "idle_time_s" in data, f"Node {node} missing idle_time_s"

    def test_congestion_scores_in_range(self):
        """All attached scores must be in [0.0, 1.0]."""
        G = make_graph_with_nodes(
            (0, False, "service"),
            (8, True,  "primary"),
            (3, True,  "secondary"),
        )
        apply_congestion_to_graph(G, config)
        for node, data in G.nodes(data=True):
            s = data["congestion_score"]
            assert 0.0 <= s <= 1.0, f"Node {node} has out-of-range score: {s}"

    def test_idle_time_consistent_with_score(self):
        """idle_time_s must equal congestion_score * T_BASE_IDLE for every node."""
        G = make_graph_with_nodes(
            (4, True, "primary"),
            (1, False, "residential"),
        )
        apply_congestion_to_graph(G, config)
        for node, data in G.nodes(data=True):
            expected_idle = data["congestion_score"] * config.T_BASE_IDLE
            assert abs(data["idle_time_s"] - expected_idle) < 1e-9, \
                f"Node {node}: idle={data['idle_time_s']:.4f} != score*T_BASE={expected_idle:.4f}"

    def test_high_congestion_node_higher_score(self):
        """A high-congestion node must score higher than a low-congestion node."""
        G = make_graph_with_nodes(
            (8, True, "primary"),     # node 1 - high congestion
            (1, False, "residential"), # node 2 - low congestion
        )
        apply_congestion_to_graph(G, config)
        score_high = G.nodes[1]["congestion_score"]
        score_low  = G.nodes[2]["congestion_score"]
        assert score_high > score_low, \
            f"High-congestion node should score higher: {score_high:.4f} <= {score_low:.4f}"

    def test_returns_same_graph_object(self):
        """apply_congestion_to_graph must return the same graph object (in-place)."""
        G = make_graph_with_nodes((2, False, "secondary"))
        G_returned = apply_congestion_to_graph(G, config)
        assert G_returned is G


# ---------------------------------------------------------------------------
# Phase 4 Tests: Emissions helpers (already implemented - regression only)
# ---------------------------------------------------------------------------

class TestEmissionsHelpers:

    def test_fuel_to_co2_conversion(self):
        """1000 mL (1 litre) of petrol -> 2310g CO2 (from config constant)."""
        from r2i.models.emissions import fuel_ml_to_co2_g
        co2 = fuel_ml_to_co2_g(1000.0)
        assert abs(co2 - config.CO2_PER_LITRE_PETROL) < 1e-9

    def test_fuel_to_co2_zero(self):
        """0 mL fuel -> 0 g CO2."""
        from r2i.models.emissions import fuel_ml_to_co2_g
        assert fuel_ml_to_co2_g(0.0) == 0.0

    def test_idle_co2_from_time(self):
        """30s idle at ICE_IDLE_CO2_PER_SEC must produce correct CO2."""
        from r2i.models.emissions import idle_co2_from_time
        expected = 30.0 * config.ICE_IDLE_CO2_PER_SEC
        assert abs(idle_co2_from_time(30.0) - expected) < 1e-9

    def test_idle_fuel_from_time(self):
        """60s idle must consume ICE_IDLE_ML_PER_SEC * 60 mL fuel."""
        from r2i.models.emissions import idle_fuel_from_time
        expected = 60.0 * config.ICE_IDLE_ML_PER_SEC
        assert abs(idle_fuel_from_time(60.0) - expected) < 1e-9
