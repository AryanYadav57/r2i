"""v2 physics: CO2 reporting fix, vehicle classes, payload, energy and cost."""

import networkx as nx
import pytest

from r2i import config
from r2i.models.vehicle import (
    VEHICLE_SPECS, ICEVehicle, EVVehicle, SpecVehicle, make_vehicle,
)
from r2i.routing.router import compute_eco_metrics


@pytest.fixture
def two_edge_graph():
    G = nx.MultiDiGraph()
    G.add_node(1, node_degree=2, is_signal=False, highway_class_weight=0.2)
    G.add_node(2, node_degree=8, is_signal=True, highway_class_weight=1.0)
    G.add_node(3, node_degree=1, is_signal=False, highway_class_weight=0.2)
    G.add_edge(1, 2, 0, length=1000.0, travel_time=120.0)
    G.add_edge(2, 3, 0, length=1000.0, travel_time=120.0)
    return G


class TestCo2ExcludesTimePenalty:
    def test_co2_is_cruise_plus_idle_only(self, two_edge_graph):
        v = ICEVehicle()
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], v)
        expected = v.cruise_cost(2.0) + v.idle_cost(m["total_idle_s"])
        assert m["total_co2_g"] == pytest.approx(expected)

    def test_routing_cost_includes_time_penalty(self, two_edge_graph):
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], ICEVehicle())
        assert m["routing_cost"] == pytest.approx(
            m["total_co2_g"] + config.ALPHA * 240.0)

    def test_ev_co2_zero_but_routing_cost_positive(self, two_edge_graph):
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], EVVehicle())
        assert m["total_co2_g"] == 0.0
        assert m["routing_cost"] > 0.0


class TestFuelEnergyCost:
    def test_ice_fuel_includes_cruise(self, two_edge_graph):
        v = ICEVehicle()
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], v)
        assert m["fuel_ml"] > v.idle_fuel(m["total_idle_s"])

    def test_ice_cost_inr_matches_fuel(self, two_edge_graph):
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], ICEVehicle())
        assert m["cost_inr"] == pytest.approx(
            m["fuel_ml"] / 1000 * config.FUEL_PRICE_INR_PER_L["petrol"])

    def test_ev_reports_energy_and_grid_co2(self, two_edge_graph):
        m = compute_eco_metrics(two_edge_graph, [1, 2, 3], EVVehicle())
        assert m["energy_kwh"] > 0.0
        assert m["fuel_ml"] == 0.0
        assert m["grid_co2_g"] == pytest.approx(
            m["energy_kwh"] * config.GRID_CO2_G_PER_KWH)
        assert m["cost_inr"] == pytest.approx(
            m["energy_kwh"] * config.ELECTRICITY_INR_PER_KWH)


class TestVehicleClasses:
    @pytest.mark.parametrize("key", list(VEHICLE_SPECS))
    def test_every_class_constructs_with_non_negative_costs(self, key):
        v = make_vehicle(key)
        assert v.cruise_cost(1.0) >= 0 and v.idle_cost(10) >= 0
        assert v.fuel_ml(1.0, 10) >= 0 and v.energy_kwh(1.0) >= 0

    def test_legacy_names_still_work(self):
        assert make_vehicle("ICE").name == "ICE"
        assert make_vehicle("ev").name == "EV"

    def test_unknown_class_raises(self):
        with pytest.raises(ValueError):
            make_vehicle("hovercraft")

    def test_electric_classes_have_zero_tailpipe(self):
        for key, spec in VEHICLE_SPECS.items():
            if spec.fuel == "electric":
                assert make_vehicle(key).cruise_cost(5.0) == 0.0

    def test_diesel_van_emits_more_than_petrol_2w(self):
        assert make_vehicle("van_diesel").cruise_cost(1) > make_vehicle("2w_petrol").cruise_cost(1)


class TestPayload:
    def test_payload_increases_cruise_cost(self):
        empty = make_vehicle("van_diesel")
        full = empty.with_payload(600)
        assert full.cruise_cost(1.0) > empty.cruise_cost(1.0)

    def test_payload_increases_ev_energy(self):
        empty = make_vehicle("van_ev")
        assert empty.with_payload(500).energy_kwh(1.0) > empty.energy_kwh(1.0)

    def test_payload_does_not_change_idle(self):
        v = make_vehicle("van_diesel")
        assert v.with_payload(600).idle_cost(30) == v.idle_cost(30)

    def test_payload_over_capacity_raises(self):
        v = make_vehicle("2w_petrol")
        with pytest.raises(ValueError):
            v.with_payload(v.spec.capacity_kg + 1)

    def test_with_payload_returns_new_instance(self):
        v = make_vehicle("van_ev")
        assert v.with_payload(100) is not v and v.payload_kg == 0

    def test_specvehicle_is_vehiclemodel(self):
        from r2i.models.vehicle import VehicleModel
        assert isinstance(make_vehicle("3w_ev"), (SpecVehicle, VehicleModel))


class TestNodeDegree:
    def test_uses_osm_street_count_when_present(self):
        from r2i.graph.features import compute_node_degrees
        G = nx.MultiDiGraph()
        G.add_node(1, street_count=3)
        for n in (2, 3, 4):
            G.add_node(n, street_count=1)
            G.add_edge(1, n); G.add_edge(n, 1)   # two-way streets
        compute_node_degrees(G)
        assert G.nodes[1]["node_degree"] == 3     # not 6 (in+out)

    def test_falls_back_to_undirected_neighbours(self):
        from r2i.graph.features import compute_node_degrees
        G = nx.MultiDiGraph()
        G.add_edge(1, 2); G.add_edge(2, 1); G.add_edge(1, 3)
        compute_node_degrees(G)
        assert G.nodes[1]["node_degree"] == 2
