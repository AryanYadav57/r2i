"""
tests/test_cost.py - Vehicle Model & Edge Cost Function Tests
Route-to-Impact (R2I) - Phase 5 & Phase 6 Exit Gate

All Phase 5 and Phase 6 tests are ACTIVE.
Phase 7 tests remain SKIPPED until router.py is implemented.

Key Invariants:
  [Phase 5] ICE/EV divergence, cost formulas, factory
  [Phase 6] Monotonicity, finiteness, non-negativity, ICE>EV on congested link,
            breakdown dict keys, graph-level weight application
"""

import math
import pytest
import networkx as nx

from r2i import config
from r2i.models.vehicle import ICEVehicle, EVVehicle, VehicleModel, make_vehicle
from r2i.routing.cost import (
    compute_edge_weight,
    compute_edge_weight_breakdown,
    apply_weights_to_graph,
)
from r2i.models.congestion import apply_congestion_to_graph


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SHORT_EDGE = {"length": 100.0, "travel_time": 12.0, "speed_kph": 30.0}
LONG_EDGE  = {"length": 800.0, "travel_time": 96.0, "speed_kph": 30.0}

LOW_NODE  = {"node_degree": 1, "is_signal": False, "highway_class_weight": 0.2}
HIGH_NODE = {"node_degree": 6, "is_signal": True,  "highway_class_weight": 1.0}
ZERO_NODE = {"node_degree": 0, "is_signal": False, "highway_class_weight": 0.1}


# ---------------------------------------------------------------------------
# Phase 5 Tests: ICEVehicle
# ---------------------------------------------------------------------------

class TestICEVehicle:

    def test_is_vehicle_model_subclass(self):
        assert issubclass(ICEVehicle, VehicleModel)
        assert not getattr(ICEVehicle, "__abstractmethods__", set())

    def test_name_is_ice(self):
        assert ICEVehicle().name == "ICE"

    def test_cruise_cost_positive_for_positive_distance(self):
        assert ICEVehicle().cruise_cost(1.0) > 0.0

    def test_cruise_cost_zero_for_zero_distance(self):
        assert ICEVehicle().cruise_cost(0.0) == 0.0

    @pytest.mark.parametrize("dist_km", [0.1, 0.5, 1.0, 5.0, 10.0, 50.0])
    def test_cruise_cost_formula(self, dist_km):
        v = ICEVehicle()
        assert abs(v.cruise_cost(dist_km) - v.E_CRUISE_G_PER_KM * dist_km) < 1e-9

    def test_cruise_cost_monotonic(self):
        v = ICEVehicle()
        assert v.cruise_cost(2.0) > v.cruise_cost(1.0)

    def test_cruise_cost_finite(self):
        assert math.isfinite(ICEVehicle().cruise_cost(100.0))

    def test_cruise_cost_non_negative(self):
        assert ICEVehicle().cruise_cost(0.0) >= 0.0

    def test_idle_cost_positive_for_positive_time(self):
        assert ICEVehicle().idle_cost(30.0) > 0.0

    def test_idle_cost_zero_for_zero_time(self):
        assert ICEVehicle().idle_cost(0.0) == 0.0

    @pytest.mark.parametrize("idle_s", [1.0, 10.0, 17.5, 30.0, 60.0])
    def test_idle_cost_formula(self, idle_s):
        v = ICEVehicle()
        assert abs(v.idle_cost(idle_s) - v.E_IDLE_G_PER_SEC * idle_s) < 1e-9

    def test_idle_cost_consistent_with_config(self):
        assert abs(ICEVehicle().idle_cost(1.0) - config.ICE_IDLE_CO2_PER_SEC) < 1e-9

    def test_idle_fuel_positive_for_positive_time(self):
        assert ICEVehicle().idle_fuel(30.0) > 0.0

    def test_idle_fuel_zero_for_zero_time(self):
        assert ICEVehicle().idle_fuel(0.0) == 0.0

    def test_idle_fuel_formula(self):
        v = ICEVehicle()
        assert abs(v.idle_fuel(60.0) - config.ICE_IDLE_ML_PER_SEC * 60.0) < 1e-9

    def test_idle_cost_and_fuel_consistent(self):
        v = ICEVehicle()
        co2 = v.idle_cost(30.0); fuel = v.idle_fuel(30.0)
        assert abs(co2 / fuel - config.CO2_PER_LITRE_PETROL / 1000.0) < 1e-9


class TestEVVehicle:

    def test_is_vehicle_model_subclass(self):
        assert issubclass(EVVehicle, VehicleModel)
        assert not getattr(EVVehicle, "__abstractmethods__", set())

    def test_name_is_ev(self):
        assert EVVehicle().name == "EV"

    @pytest.mark.parametrize("dist_km", [0.0, 0.1, 1.0, 10.0, 100.0])
    def test_cruise_cost_always_zero(self, dist_km):
        assert EVVehicle().cruise_cost(dist_km) == 0.0

    @pytest.mark.parametrize("idle_s", [0.0, 1.0, 17.5, 60.0, 3600.0])
    def test_idle_cost_always_zero(self, idle_s):
        assert EVVehicle().idle_cost(idle_s) == 0.0

    @pytest.mark.parametrize("idle_s", [0.0, 30.0, 120.0])
    def test_idle_fuel_always_zero(self, idle_s):
        assert EVVehicle().idle_fuel(idle_s) == 0.0


class TestVehicleDivergence:

    def test_idle_cost_diverges(self):
        assert ICEVehicle().idle_cost(30.0) != EVVehicle().idle_cost(30.0)

    def test_cruise_cost_diverges(self):
        assert ICEVehicle().cruise_cost(1.0) != EVVehicle().cruise_cost(1.0)

    def test_ice_idle_cost_greater_than_ev(self):
        assert ICEVehicle().idle_cost(30.0) > EVVehicle().idle_cost(30.0)

    def test_ice_cruise_cost_greater_than_ev(self):
        assert ICEVehicle().cruise_cost(5.0) > EVVehicle().cruise_cost(5.0)

    def test_polymorphic_call_same_interface(self):
        for v in [ICEVehicle(), EVVehicle()]:
            cost = v.cruise_cost(1.0) + v.idle_cost(10.0) + v.idle_fuel(10.0)
            assert cost >= 0.0


class TestMakeVehicleFactory:

    def test_make_ice(self):
        assert isinstance(make_vehicle("ICE"), ICEVehicle)

    def test_make_ev(self):
        assert isinstance(make_vehicle("EV"), EVVehicle)

    def test_case_insensitive(self):
        assert isinstance(make_vehicle("ice"), ICEVehicle)
        assert isinstance(make_vehicle("ev"),  EVVehicle)

    def test_whitespace_stripped(self):
        assert isinstance(make_vehicle("  ICE  "), ICEVehicle)

    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown vehicle type"):
            make_vehicle("DIESEL")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            make_vehicle("")


# ---------------------------------------------------------------------------
# Phase 6 Tests: compute_edge_weight
# ---------------------------------------------------------------------------

class TestComputeEdgeWeight:

    def test_returns_float(self):
        """compute_edge_weight must return a float."""
        w = compute_edge_weight(SHORT_EDGE, LOW_NODE, ICEVehicle(), config)
        assert isinstance(w, float)

    def test_non_negative_ice_low_congestion(self):
        """ICE weight on low-congestion node must be >= 0."""
        w = compute_edge_weight(SHORT_EDGE, LOW_NODE, ICEVehicle(), config)
        assert w >= 0.0

    def test_non_negative_ev_high_congestion(self):
        """EV weight on high-congestion node must be >= 0."""
        w = compute_edge_weight(LONG_EDGE, HIGH_NODE, EVVehicle(), config)
        assert w >= 0.0

    def test_finite_all_combinations(self):
        """All edge weight computations must be finite."""
        for v in [ICEVehicle(), EVVehicle()]:
            for edge in [SHORT_EDGE, LONG_EDGE]:
                for node in [LOW_NODE, HIGH_NODE, ZERO_NODE]:
                    w = compute_edge_weight(edge, node, v, config)
                    assert math.isfinite(w), \
                        f"Non-finite weight {w} for {v.name}/{edge}/{node}"

    def test_monotonicity_length_ice(self):
        """Longer edge must produce strictly higher W_edge for ICE."""
        w_short = compute_edge_weight(SHORT_EDGE, LOW_NODE, ICEVehicle(), config)
        w_long  = compute_edge_weight(LONG_EDGE,  LOW_NODE, ICEVehicle(), config)
        assert w_long > w_short, \
            f"Monotonicity violated: short={w_short:.4f}  long={w_long:.4f}"

    def test_monotonicity_length_ev(self):
        """Longer edge must produce strictly higher W_edge for EV (time penalty)."""
        w_short = compute_edge_weight(SHORT_EDGE, LOW_NODE, EVVehicle(), config)
        w_long  = compute_edge_weight(LONG_EDGE,  LOW_NODE, EVVehicle(), config)
        assert w_long > w_short

    def test_ice_higher_than_ev_on_congested_node(self):
        """ICE must have strictly higher weight than EV on high-congestion node."""
        w_ice = compute_edge_weight(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        w_ev  = compute_edge_weight(SHORT_EDGE, HIGH_NODE, EVVehicle(),  config)
        assert w_ice > w_ev, \
            f"ICE ({w_ice:.4f}) must exceed EV ({w_ev:.4f}) on congested node"

    def test_ev_weight_driven_only_by_time(self):
        """
        EV has zero emission costs, so its weight must equal alpha * travel_time.
        """
        w = compute_edge_weight(SHORT_EDGE, HIGH_NODE, EVVehicle(), config)
        expected = config.ALPHA * SHORT_EDGE["travel_time"]
        assert abs(w - expected) < 1e-9, \
            f"EV weight {w:.6f} != alpha*t {expected:.6f}"

    def test_ice_weight_formula_manual(self):
        """
        Verify ICE weight on SHORT_EDGE + ZERO_NODE using the exact breakdown.
        ZERO_NODE has highway_class_weight=0.1 which produces a tiny but
        non-zero congestion score, so we use breakdown to get exact components.
        W = cruise_co2 + idle_co2 + alpha * travel_time
        """
        bd = compute_edge_weight_breakdown(SHORT_EDGE, ZERO_NODE, ICEVehicle(), config)
        w  = compute_edge_weight(SHORT_EDGE, ZERO_NODE, ICEVehicle(), config)
        # Cruise component: 120 g/km * 0.1 km = 12.0 g
        expected_cruise = config.ICE_CRUISE_CO2_PER_KM * (SHORT_EDGE["length"] / 1000.0)
        assert abs(bd["cruise_co2_g"] - expected_cruise) < 1e-9
        # Time component: ALPHA * travel_time
        expected_time = config.ALPHA * SHORT_EDGE["travel_time"]
        assert abs(bd["time_penalty"] - expected_time) < 1e-9
        # Total must equal sum of three components exactly
        assert abs(w - (bd["cruise_co2_g"] + bd["idle_co2_g"] + bd["time_penalty"])) < 1e-9

    def test_higher_congestion_higher_ice_weight(self):
        """Same edge, higher congestion node -> strictly higher ICE weight."""
        w_low  = compute_edge_weight(SHORT_EDGE, LOW_NODE,  ICEVehicle(), config)
        w_high = compute_edge_weight(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        assert w_high > w_low, \
            f"Higher congestion must increase ICE weight: low={w_low:.4f} high={w_high:.4f}"

    def test_missing_length_uses_default(self):
        """If edge has no 'length', weight must still be computed (no KeyError)."""
        edge_no_len = {"travel_time": 12.0, "speed_kph": 30.0}
        w = compute_edge_weight(edge_no_len, LOW_NODE, ICEVehicle(), config)
        assert w >= 0.0 and math.isfinite(w)

    def test_missing_travel_time_uses_zero(self):
        """If edge has no 'travel_time', time penalty must be zero."""
        edge_no_tt = {"length": 100.0, "speed_kph": 30.0}
        w_no_tt  = compute_edge_weight(edge_no_tt,  LOW_NODE, ICEVehicle(), config)
        w_with_tt = compute_edge_weight(SHORT_EDGE, LOW_NODE, ICEVehicle(), config)
        # Without travel_time, weight should be less than with travel_time
        assert w_no_tt <= w_with_tt


class TestComputeEdgeWeightBreakdown:

    def test_returns_required_keys(self):
        """Breakdown dict must contain all required keys."""
        bd = compute_edge_weight_breakdown(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        required = {
            "cruise_co2_g", "idle_co2_g", "time_penalty",
            "congestion_score", "idle_time_s", "total_weight", "fuel_ml"
        }
        assert required <= set(bd.keys()), \
            f"Missing keys: {required - set(bd.keys())}"

    def test_total_equals_sum_of_components(self):
        """total_weight must equal cruise + idle + time_penalty."""
        bd = compute_edge_weight_breakdown(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        expected = bd["cruise_co2_g"] + bd["idle_co2_g"] + bd["time_penalty"]
        assert abs(bd["total_weight"] - expected) < 1e-9

    def test_breakdown_matches_compute_edge_weight(self):
        """total_weight in breakdown must match compute_edge_weight() exactly."""
        w  = compute_edge_weight(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        bd = compute_edge_weight_breakdown(SHORT_EDGE, HIGH_NODE, ICEVehicle(), config)
        assert abs(bd["total_weight"] - w) < 1e-9

    def test_ev_cruise_and_idle_zero_in_breakdown(self):
        """EV breakdown must show 0.0 for cruise_co2_g and idle_co2_g."""
        bd = compute_edge_weight_breakdown(SHORT_EDGE, HIGH_NODE, EVVehicle(), config)
        assert bd["cruise_co2_g"] == 0.0
        assert bd["idle_co2_g"]   == 0.0
        assert bd["fuel_ml"]      == 0.0

    def test_congestion_score_in_valid_range(self):
        """Breakdown congestion_score must be in [0.0, 1.0]."""
        bd = compute_edge_weight_breakdown(LONG_EDGE, HIGH_NODE, ICEVehicle(), config)
        assert 0.0 <= bd["congestion_score"] <= 1.0

    def test_idle_time_consistent_with_score(self):
        """idle_time_s must equal congestion_score * T_BASE_IDLE."""
        bd = compute_edge_weight_breakdown(SHORT_EDGE, LOW_NODE, ICEVehicle(), config)
        expected_idle = bd["congestion_score"] * config.T_BASE_IDLE
        assert abs(bd["idle_time_s"] - expected_idle) < 1e-9


class TestApplyWeightsToGraph:

    @pytest.fixture
    def weighted_graph(self):
        """Graph with features and congestion already applied."""
        G = nx.MultiDiGraph()
        G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
        G.add_node(2, node_degree=4, is_signal=True,  highway_class_weight=1.0)
        G.add_node(3, node_degree=2, is_signal=False, highway_class_weight=0.3)
        G.add_edge(1, 2, 0, length=200.0, travel_time=24.0,
                   speed_kph=30.0, highway="primary")
        G.add_edge(2, 3, 0, length=200.0, travel_time=24.0,
                   speed_kph=30.0, highway="primary")
        G.add_edge(1, 3, 0, length=500.0, travel_time=60.0,
                   speed_kph=30.0, highway="residential")
        apply_congestion_to_graph(G, config)
        return G

    def test_all_edges_get_r2i_weight(self, weighted_graph):
        """Every edge must have 'r2i_weight' after apply_weights_to_graph."""
        apply_weights_to_graph(weighted_graph, ICEVehicle(), config)
        for u, v, key, data in weighted_graph.edges(keys=True, data=True):
            assert "r2i_weight" in data, \
                f"Edge ({u},{v},{key}) missing r2i_weight"

    def test_all_weights_non_negative(self, weighted_graph):
        """All r2i_weight values must be >= 0."""
        apply_weights_to_graph(weighted_graph, ICEVehicle(), config)
        for u, v, key, data in weighted_graph.edges(keys=True, data=True):
            assert data["r2i_weight"] >= 0.0

    def test_all_weights_finite(self, weighted_graph):
        """All r2i_weight values must be finite."""
        apply_weights_to_graph(weighted_graph, EVVehicle(), config)
        for u, v, key, data in weighted_graph.edges(keys=True, data=True):
            assert math.isfinite(data["r2i_weight"])

    def test_returns_same_graph_object(self, weighted_graph):
        """apply_weights_to_graph must return the same graph object (in-place)."""
        G_returned = apply_weights_to_graph(weighted_graph, ICEVehicle(), config)
        assert G_returned is weighted_graph

    def test_congested_edge_heavier_for_ice(self, weighted_graph):
        """Edge to congested node 2 must weigh more than edge to uncongested node 3."""
        apply_weights_to_graph(weighted_graph, ICEVehicle(), config)
        # Edge 1->2 (dest=2, congested) vs 1->3 (dest=3, not congested), same length
        # We compare by dest node congestion rather than edge distance
        w_to_2 = weighted_graph[1][2][0]["r2i_weight"]
        w_to_3 = weighted_graph[1][3][0]["r2i_weight"]
        # Note: edge 1->3 is 500m vs 1->2 is 200m, so we check 2->3 vs 1->3
        # Both edges go to node 3 (low congestion) vs node 2 (high congestion)
        # 1->2: length=200m, dest=high congestion
        # 2->3: length=200m, dest=low congestion
        w_1_2 = weighted_graph[1][2][0]["r2i_weight"]
        w_2_3 = weighted_graph[2][3][0]["r2i_weight"]
        assert w_1_2 > w_2_3, \
            f"Edge to congested node ({w_1_2:.4f}) should exceed edge to quiet node ({w_2_3:.4f})"
