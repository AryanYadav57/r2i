"""Fleet planner invariants on a small synthetic grid."""

import networkx as nx
import pytest

from r2i.fleet import RoadNetwork, generate_scenario, plan_fleet
from r2i.fleet.model import FleetVehicle, Hub, Order, Scenario
from r2i.models.congestion import apply_congestion_to_graph


def grid_graph(n=7, spacing_m=200.0):
    """n x n two-way grid; centre column is a busy signalised primary road."""
    G = nx.MultiDiGraph()
    deg = 1.0 / 111_000 * spacing_m
    for i in range(n):
        for j in range(n):
            busy = j == n // 2
            G.add_node((i, j), x=77.6 + j * deg, y=12.93 + i * deg,
                       node_degree=4 if busy else 3, is_signal=busy,
                       highway_class_weight=1.0 if busy else 0.2)
    for i in range(n):
        for j in range(n):
            for di, dj in ((0, 1), (1, 0)):
                a, b = (i, j), (i + di, j + dj)
                if b in G:
                    for u, v in ((a, b), (b, a)):
                        G.add_edge(u, v, length=spacing_m, travel_time=spacing_m / 8.0)
    G = nx.convert_node_labels_to_integers(G)
    apply_congestion_to_graph(G)
    return G


@pytest.fixture(scope="module")
def net():
    return RoadNetwork(grid_graph())


@pytest.fixture(scope="module")
def scenario(net):
    return generate_scenario(net, n_orders=12, seed=7,
                             hub_lat=12.93 + 3 * 200 / 111_000,
                             hub_lon=77.6 + 3 * 200 / 111_000,
                             fleet=["van_diesel", "3w_ev", "2w_petrol"],
                             radius_m=1500)


@pytest.fixture(scope="module")
def result(net, scenario):
    return plan_fleet(net, scenario, time_limit_s=1)


class TestNetwork:
    def test_nearest_returns_closest_node(self, net):
        idx = net.nearest(12.93, 77.6)
        assert net.lat[idx] == pytest.approx(12.93)

    def test_path_stats_positive(self, net):
        dist, pred = net.dijkstra([0], "distance")
        path = net.path(pred[0], 0, net.n - 1)
        stats = net.path_stats(path)
        assert path[0] == 0 and path[-1] == net.n - 1
        assert stats["length_km"] == pytest.approx(dist[0][net.n - 1], rel=1e-6)


class TestScenario:
    def test_deterministic(self, net, scenario):
        again = generate_scenario(net, n_orders=12, seed=7,
                                  hub_lat=scenario.hub.lat, hub_lon=scenario.hub.lon,
                                  fleet=["van_diesel", "3w_ev", "2w_petrol"], radius_m=1500)
        assert [o.node for o in again.orders] == [o.node for o in scenario.orders]

    def test_windows_are_valid(self, scenario):
        for o in scenario.orders:
            assert o.tw_start_s < o.tw_end_s and o.weight_kg > 0


@pytest.mark.parametrize("plan_key", ["baseline", "r2i"])
class TestPlanInvariants:
    def test_every_order_served_once_or_unserved(self, result, scenario, plan_key):
        plan = result[plan_key]
        served = [s["order_id"] for v in plan["vehicles"] for s in v["stops"]]
        assert len(served) == len(set(served))
        assert set(served) | set(plan["unserved"]) == {o.id for o in scenario.orders}

    def test_capacity_respected(self, result, scenario, plan_key):
        caps = {v.id: v.spec.capacity_kg for v in scenario.vehicles}
        for v in result[plan_key]["vehicles"]:
            assert v["start_load_kg"] <= caps[v["id"]] + 1e-9
            loads = [s["load_after_kg"] for s in v["stops"]]
            assert all(a >= b for a, b in zip(loads, loads[1:]))

    def test_time_windows_respected(self, result, scenario, plan_key):
        tw = {o.id: (o.tw_start_s, o.tw_end_s) for o in scenario.orders}
        for v in result[plan_key]["vehicles"]:
            for s in v["stops"]:
                lo, hi = tw[s["order_id"]]
                assert lo - 1 <= s["start_s"] <= hi + 1

    def test_trajectory_times_non_decreasing(self, result, plan_key):
        for v in result[plan_key]["vehicles"]:
            ts = [p[2] for p in v["trajectory"]]
            assert ts == sorted(ts) and len(ts) >= 2

    def test_ev_tailpipe_zero(self, result, scenario, plan_key):
        electric = {v.id for v in scenario.vehicles if v.spec.is_electric}
        for v in result[plan_key]["vehicles"]:
            if v["id"] in electric:
                assert v["metrics"]["co2_g"] == 0.0

    def test_totals_sum_vehicle_metrics(self, result, plan_key):
        plan = result[plan_key]
        assert plan["totals"]["co2_g"] == pytest.approx(
            sum(v["metrics"]["co2_g"] for v in plan["vehicles"]))


class TestComparison:
    def test_same_constraints_both_plans(self, result):
        assert result["baseline"]["vehicle_ids"] == result["r2i"]["vehicle_ids"]

    def test_insights_have_text(self, result):
        assert result["insights"] and all(i["title"] for i in result["insights"])

    def test_comparison_keys(self, result):
        for k in ("co2_g", "fuel_ml", "cost_inr", "distance_km", "on_time_pct"):
            assert k in result["comparison"]["baseline"] and k in result["comparison"]["r2i"]

    def test_payload_reorder_never_worse(self, result):
        for v in result["r2i"]["vehicles"]:
            assert v["objective_after_reorder"] <= v["objective_before_reorder"] + 1e-6


def test_infeasible_order_is_reported_unserved(net):
    hub = Hub(net.lat[0], net.lon[0], 0)
    orders = [Order("big", net.lat[5], net.lon[5], 5, weight_kg=5000.0,
                    tw_start_s=32400, tw_end_s=43200)]
    sc = Scenario(hub, orders, [FleetVehicle.of("v1", "2w_petrol")])
    res = plan_fleet(net, sc, time_limit_s=1)
    assert res["r2i"]["unserved"] == ["big"]


def test_all_vehicles_dispatched_when_enough_orders(result, scenario):
    for key in ("baseline", "r2i"):
        assert len(result[key]["vehicles"]) == len(scenario.vehicles)


def test_headline_sign_reports_reduction(result):
    head = result["insights"][0]["title"]
    d = result["comparison"]["delta"]["co2_g"]
    assert ("-" in head.split("(")[1]) == (d < 0)


def test_vehicle_that_fits_nothing_does_not_drop_all_orders(net):
    hub = Hub(*net.coords(24), 24)
    orders = [Order(f"O{i}", *net.coords(n), n, 30.0, 32400, 46800) for i, n in enumerate((3, 10, 40))]
    sc = Scenario(hub, orders, [FleetVehicle.of("v", "van_diesel"), FleetVehicle.of("b", "2w_petrol")])
    res = plan_fleet(net, sc, time_limit_s=1)
    for key in ("baseline", "r2i"):
        assert res[key]["unserved"] == []


@pytest.mark.parametrize("seed", range(30, 40))
def test_plans_never_late_or_over_shift(seed):
    """Tight windows on a grid with fractional edge times (reviewer repro)."""
    import random
    net = RoadNetwork(grid_graph(9, 403.6))
    hub, rng = 40, random.Random(seed)
    orders = []
    for i, node in enumerate(rng.sample([i for i in range(net.n) if i != hub], 12)):
        s = 9 * 3600 + rng.randint(0, 2 * 3600)
        orders.append(Order(f"O{i}", *net.coords(node), node, round(rng.uniform(1, 60), 1),
                            s, s + rng.randint(60, 600)))
    se = 9 * 3600 + rng.randint(2 * 3600 + 600, 3 * 3600)
    vs = [FleetVehicle.of("v1", "van_diesel", shift_end_s=se), FleetVehicle.of("e1", "3w_ev", shift_end_s=se)]
    res = plan_fleet(net, Scenario(Hub(*net.coords(hub), hub), orders, vs), 0.3)
    for key in ("baseline", "r2i"):
        for v in res[key]["vehicles"]:
            assert v["metrics"]["late_s"] == 0, (key, v["id"])
            assert v["return_s"] <= se + 1e-6, (key, v["id"])


def _toy(travel_s, windows, weights, length_km=1.0):
    """Hand-made legs: hub + len(windows) orders, every leg identical."""
    import numpy as np
    from r2i.fleet.solver import Legs
    m = len(windows) + 1
    full = lambda v: np.full((m, m), v) - np.diag(np.full(m, v))  # noqa: E731
    legs = Legs("toy", list(range(m)), full(length_km), full(length_km), full(travel_s),
                np.zeros((m, m)), np.zeros((m, 1)))
    orders = [Order(f"O{i + 1}", 0, 0, i + 1, w, lo, hi) for i, ((lo, hi), w) in enumerate(zip(windows, weights))]
    return legs, orders


def test_solver_time_rounding_never_produces_late_stops():
    from r2i.fleet.solver import evaluate_route, solve_vrp
    legs, orders = _toy(50.45, [(32400 + 50, 32400 + 50)], [5])
    veh = FleetVehicle.of("v", "van_diesel")
    sc = Scenario(Hub(0, 0, 0), orders, [veh])
    routes, _ = solve_vrp(sc, [legs], 1)
    if routes[0]:
        assert evaluate_route(sc, veh, legs, routes[0])["metrics"]["late_s"] == 0


def test_reorder_never_increases_total_lateness():
    from r2i.fleet.solver import evaluate_route, reorder_for_payload
    # [O2, O1]: O1 late by 1 s.  [O1, O2]: cheaper (heavy first) but O2 late by 120 s.
    legs, orders = _toy(100.0, [(32400, 32719), (32400, 32600)], [500, 10])
    veh = FleetVehicle.of("v", "van_diesel")
    sc = Scenario(Hub(0, 0, 0), orders, [veh])
    before = evaluate_route(sc, veh, legs, [2, 1])["metrics"]["late_s"]
    seq = reorder_for_payload(sc, veh, legs, [2, 1])
    assert evaluate_route(sc, veh, legs, seq)["metrics"]["late_s"] <= before
