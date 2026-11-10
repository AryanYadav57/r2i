"""
fleet/solver.py - Fleet planning: cost matrices, OR-Tools CVRPTW,
payload-aware evaluation and stop re-ordering, simulation output.

Two plans are produced for the same scenario and constraints:
  baseline : every vehicle routes and is assigned on shortest distance
  r2i      : each vehicle class uses its own R2I cost (CO2 + alpha * time),
             then stops are re-ordered within each route using the true
             payload-aware cost (heavy parcels early when it pays off).
Both plans are scored with the same payload-aware physics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from r2i import config
from r2i.fleet.model import FleetVehicle, Scenario
from r2i.fleet.network import RoadNetwork
from r2i.models.vehicle import SpecVehicle

COST_SCALE = 100          # solver works in integers
UNREACHABLE = 10**8
DROP_PENALTY = 10**10
IDLE_EVENT_S = 6.0        # idle stops shorter than this are not emitted as events


@dataclass
class Legs:
    """Point-to-point leg data between hub (index 0) and orders, for one objective."""
    objective: str
    points: list
    cost: np.ndarray
    length: np.ndarray
    travel: np.ndarray
    idle: np.ndarray
    pred: np.ndarray

    def path(self, net: RoadNetwork, i: int, j: int) -> list:
        return net.path(self.pred[i], self.points[i], self.points[j])


def build_legs(net: RoadNetwork, points: list, objective: str) -> Legs:
    dist, pred = net.dijkstra(points, objective)
    m = len(points)
    length, travel, idle = (np.zeros((m, m)) for _ in range(3))
    cost = dist[:, points]
    for i in range(m):
        for j in range(m):
            if i == j or not math.isfinite(cost[i, j]):
                continue
            s = net.path_stats(net.path(pred[i], points[i], points[j]))
            length[i, j], travel[i, j], idle[i, j] = s["length_km"], s["travel_s"], s["idle_s"]
    return Legs(objective, points, cost, length, travel, idle, pred)


# --------------------------------------------------------------------------- solver
def solve_vrp(scn: Scenario, legs_per_vehicle: list, time_limit_s: float = 3.0):
    """Return (routes: list[list[order_pos]], unserved_ids).

    Every vehicle that can carry at least one order is dispatched (a driver on
    shift gets work). If that makes the model infeasible, solve again without it.
    """
    routes = _solve_vrp(scn, legs_per_vehicle, time_limit_s, force_dispatch=True)
    if routes is None:
        routes = _solve_vrp(scn, legs_per_vehicle, time_limit_s, force_dispatch=False)
    routes = routes or [[] for _ in scn.vehicles]
    served = {k for r in routes for k in r}
    unserved = [o.id for k, o in enumerate(scn.orders, start=1) if k not in served]
    return routes, unserved


def _solve_vrp(scn: Scenario, legs_per_vehicle: list, time_limit_s: float, force_dispatch: bool):
    orders, vehicles = scn.orders, scn.vehicles
    m, V = len(orders) + 1, len(vehicles)
    manager = pywrapcp.RoutingIndexManager(m, V, 0)
    routing = pywrapcp.RoutingModel(manager)
    node = manager.IndexToNode
    keep = []   # keep python callables alive

    def reg2(matrix):
        fn = lambda a, b, M=matrix: M[node(a)][node(b)]  # noqa: E731
        keep.append(fn)
        return routing.RegisterTransitCallback(fn)

    service = [0] + [int(o.service_s) for o in orders]
    time_cbs, dist_cbs = [], []
    for v, L in enumerate(legs_per_vehicle):
        C = np.where(np.isfinite(L.cost), np.round(L.cost * COST_SCALE), UNREACHABLE)
        routing.SetArcCostEvaluatorOfVehicle(reg2(C.astype(np.int64).tolist()), v)
        # ceil: solver times are never shorter than the evaluated float times
        T = np.ceil(L.travel + L.idle - 1e-9).astype(np.int64) + np.array(service)[:, None]
        time_cbs.append(reg2(T.tolist()))
        dist_cbs.append(reg2(np.round(L.length * 1000).astype(np.int64).tolist()))

    demand = [0] + [int(math.ceil(o.weight_kg * 10)) for o in orders]
    dfn = lambda a: demand[node(a)]  # noqa: E731
    keep.append(dfn)
    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(dfn), 0,
        [int(veh.spec.capacity_kg * 10) for veh in vehicles], True, "Load")
    routing.AddDimensionWithVehicleTransits(time_cbs, 6 * 3600, 24 * 3600, False, "Time")
    routing.AddDimensionWithVehicleTransitAndCapacity(
        dist_cbs, 0, [int(veh.range_km * 1000) for veh in vehicles], True, "Dist")

    td = routing.GetDimensionOrDie("Time")
    for k, o in enumerate(orders, start=1):
        idx = manager.NodeToIndex(k)
        td.CumulVar(idx).SetRange(int(o.tw_start_s), int(o.tw_end_s))
        routing.AddDisjunction([idx], DROP_PENALTY)
    for v, veh in enumerate(vehicles):
        for idx in (routing.Start(v), routing.End(v)):
            td.CumulVar(idx).SetRange(int(veh.shift_start_s), int(veh.shift_end_s))

    lightest = min((o.weight_kg for o in orders), default=0.0)
    if force_dispatch and len(orders) >= V:   # same rule for both plans
        for v, veh in enumerate(vehicles):
            if veh.spec.capacity_kg >= lightest:
                routing.solver().Add(routing.NextVar(routing.Start(v)) != routing.End(v))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    params.time_limit.FromMilliseconds(int(time_limit_s * 1000))
    sol = routing.SolveWithParameters(params)

    if sol is None:
        return None
    routes = [[] for _ in vehicles]
    for v in range(V):
        idx = sol.Value(routing.NextVar(routing.Start(v)))
        while not routing.IsEnd(idx):
            routes[v].append(node(idx))
            idx = sol.Value(routing.NextVar(idx))
    return routes


# ----------------------------------------------------------------------- evaluation
def evaluate_route(scn: Scenario, veh: FleetVehicle, L: Legs, seq: list,
                   cfg=config) -> dict:
    """Payload-aware metrics for one vehicle visiting order positions `seq`."""
    orders = scn.orders
    base = SpecVehicle(veh.spec)
    load = sum(orders[k - 1].weight_kg for k in seq)
    start_load = load
    acc = dict(distance_km=0.0, drive_s=0.0, idle_s=0.0, co2_g=0.0, fuel_ml=0.0,
               energy_kwh=0.0, late_stops=0, late_s=0.0)
    first = seq[0] if seq else 0
    depart = veh.shift_start_s
    if seq:
        lead = L.travel[0, first] + L.idle[0, first]
        depart = max(veh.shift_start_s, orders[first - 1].tw_start_s - lead)
    t, prev, stops, legs = depart, 0, [], []
    for k in seq + [0]:
        loaded = base.with_payload(min(max(load, 0.0), veh.spec.capacity_kg))
        ln, tr, idl = L.length[prev, k], L.travel[prev, k], L.idle[prev, k]
        acc["distance_km"] += ln
        acc["drive_s"] += tr
        acc["idle_s"] += idl
        acc["co2_g"] += loaded.cruise_cost(ln) + loaded.idle_cost(idl)
        acc["fuel_ml"] += loaded.fuel_ml(ln, idl)
        acc["energy_kwh"] += loaded.energy_kwh(ln)
        legs.append((prev, k, t, load))
        arrive = t + tr + idl
        if k == 0:
            t = arrive
            break
        o = orders[k - 1]
        start = max(arrive, o.tw_start_s)
        late = max(0.0, start - o.tw_end_s)
        engine_on = o.service_s * cfg.STOP_ENGINE_ON_FRACTION
        acc["co2_g"] += base.idle_cost(engine_on)
        acc["fuel_ml"] += base.idle_fuel(engine_on)
        acc["late_stops"] += late > 0
        acc["late_s"] += late
        load -= o.weight_kg
        stops.append(dict(order_id=o.id, lat=o.lat, lon=o.lon, weight_kg=o.weight_kg,
                          arrive_s=arrive, start_s=start, depart_s=start + o.service_s,
                          tw_start_s=o.tw_start_s, tw_end_s=o.tw_end_s,
                          load_after_kg=max(0.0, load), late_s=late))
        t = start + o.service_s
        prev = k
    acc["grid_co2_g"] = acc["energy_kwh"] * cfg.GRID_CO2_G_PER_KWH
    acc["cost_inr"] = base.energy_cost_inr(acc["fuel_ml"], acc["energy_kwh"])
    objective = acc["co2_g"] + cfg.ALPHA * (acc["drive_s"] + acc["idle_s"])
    return dict(metrics=acc, stops=stops, legs=legs, depart_s=depart, return_s=t,
                start_load_kg=start_load, objective=objective)


def reorder_for_payload(scn, veh, L, seq, max_passes=20) -> list:
    """Relocate stops within a route while the payload-aware objective improves,
    total lateness does not grow and the vehicle is back before its shift ends."""
    best = evaluate_route(scn, veh, L, seq)

    def ok(r):
        return (r["metrics"]["late_s"] <= best["metrics"]["late_s"] + 1e-9
                and (r["return_s"] <= veh.shift_end_s + 1e-6
                     or r["return_s"] <= best["return_s"] + 1e-6)
                and r["objective"] < best["objective"] - 1e-6)

    for _ in range(max_passes):
        improved = False
        for i in range(len(seq)):
            for j in range(len(seq)):
                if i == j:
                    continue
                cand = seq[:]
                cand.insert(j, cand.pop(i))
                r = evaluate_route(scn, veh, L, cand)
                if ok(r):
                    seq, best, improved = cand, r, True
        if not improved:
            break
    return seq


# ----------------------------------------------------------------------- simulation
def _trajectory(net: RoadNetwork, scn: Scenario, veh: FleetVehicle, L: Legs, ev: dict):
    """Timestamped [lon, lat, t] points, idle/stop events and visited graph nodes."""
    pts, events, visited = [], [], []
    electric = veh.spec.is_electric
    base = SpecVehicle(veh.spec)
    stop_by_pos = {i + 1: s for i, s in enumerate(ev["stops"])}
    for n, (i, j, t, load) in enumerate(ev["legs"]):
        path = L.path(net, i, j)
        if not pts:
            pts.append([float(net.lon[path[0]]), float(net.lat[path[0]]), t])
            events.append(dict(t=t, type="depart", lat=float(net.lat[path[0]]),
                               lon=float(net.lon[path[0]]), load_kg=load))
        for u, v in zip(path[:-1], path[1:]):
            e = net.edge(u, v)
            t += float(net.tt_s[e])
            lon, lat = float(net.lon[v]), float(net.lat[v])
            pts.append([lon, lat, t])
            visited.append(v)
            idle = float(net.edge_idle_s[e])
            if idle > 0:
                if idle >= IDLE_EVENT_S:
                    events.append(dict(t=t, type="idle", lat=lat, lon=lon, seconds=idle,
                                       co2_g=0.0 if electric else base.idle_cost(idle),
                                       congestion=float(net.congestion[v])))
                t += idle
                pts.append([lon, lat, t])
        if j != 0:
            s = stop_by_pos[n + 1]
            lon, lat = s["lon"], s["lat"]
            pts.append([lon, lat, s["start_s"]])
            pts.append([lon, lat, s["depart_s"]])
            events.append(dict(t=s["start_s"], type="deliver", lat=lat, lon=lon,
                               order_id=s["order_id"], load_kg=s["load_after_kg"],
                               late=s["late_s"] > 0))
            t = s["depart_s"]
        else:
            events.append(dict(t=t, type="return", lat=float(net.lat[path[-1]]),
                               lon=float(net.lon[path[-1]])))
    return pts, events, visited


# ----------------------------------------------------------------------------- plans
def build_plan(net, scn, routes, legs_per_vehicle, unserved, reorder: bool) -> dict:
    hot = float(np.quantile(net.congestion, 0.9))
    vehicles = []
    for veh, L, seq in zip(scn.vehicles, legs_per_vehicle, routes):
        if not seq:
            continue
        before = evaluate_route(scn, veh, L, seq)
        if reorder:
            seq = reorder_for_payload(scn, veh, L, seq)
        ev = evaluate_route(scn, veh, L, seq)
        traj, events, visited = _trajectory(net, scn, veh, L, ev)
        metrics = dict(ev["metrics"])
        metrics["hot_junctions"] = int(sum(net.congestion[v] >= hot for v in visited))
        vehicles.append(dict(
            id=veh.id, spec_key=veh.spec.key, label=veh.spec.label, fuel=veh.spec.fuel,
            capacity_kg=veh.spec.capacity_kg, start_load_kg=ev["start_load_kg"],
            depart_s=ev["depart_s"], return_s=ev["return_s"], stops=ev["stops"],
            metrics=metrics, trajectory=traj, events=events,
            objective_before_reorder=before["objective"],
            objective_after_reorder=ev["objective"], _visited=visited))
    return dict(vehicle_ids=[v.id for v in scn.vehicles], vehicles=vehicles,
                unserved=unserved, totals=_totals(vehicles, len(scn.orders)))


def _totals(vehicles: list, n_orders: int) -> dict:
    keys = ("distance_km", "drive_s", "idle_s", "co2_g", "fuel_ml", "energy_kwh",
            "grid_co2_g", "cost_inr", "late_stops", "hot_junctions")
    tot = {k: float(sum(v["metrics"][k] for v in vehicles)) for k in keys}
    served = sum(len(v["stops"]) for v in vehicles)
    tot.update(vehicles_used=len(vehicles), orders_served=served, orders_total=n_orders,
               on_time_pct=100.0 * (served - tot["late_stops"]) / n_orders if n_orders else 100.0,
               fuel_l=tot["fuel_ml"] / 1000.0)
    return tot


def plan_fleet(net: RoadNetwork, scn: Scenario, time_limit_s: float = 3.0) -> dict:
    """Plan the scenario twice (baseline vs R2I) and explain the difference."""
    from r2i.fleet.insights import build_insights

    points = [scn.hub.node] + [o.node for o in scn.orders]
    legs = {"distance": build_legs(net, points, "distance")}
    for key in sorted({v.spec.key for v in scn.vehicles}):
        legs[key] = build_legs(net, points, key)

    base_legs = [legs["distance"]] * len(scn.vehicles)
    r2i_legs = [legs[v.spec.key] for v in scn.vehicles]
    b_routes, b_unserved = solve_vrp(scn, base_legs, time_limit_s)
    r_routes, r_unserved = solve_vrp(scn, r2i_legs, time_limit_s)
    baseline = build_plan(net, scn, b_routes, base_legs, b_unserved, reorder=False)
    r2i = build_plan(net, scn, r_routes, r2i_legs, r_unserved, reorder=True)

    keys = ("distance_km", "co2_g", "fuel_ml", "fuel_l", "energy_kwh", "grid_co2_g",
            "cost_inr", "idle_s", "drive_s", "on_time_pct", "vehicles_used", "orders_served")
    comparison = {
        "baseline": {k: baseline["totals"][k] for k in keys},
        "r2i": {k: r2i["totals"][k] for k in keys},
        "delta": {k: r2i["totals"][k] - baseline["totals"][k] for k in keys},
    }
    insights = build_insights(net, scn, baseline, r2i, comparison)
    for plan in (baseline, r2i):
        for v in plan["vehicles"]:
            v.pop("_visited", None)
    return dict(scenario=scenario_to_dict(scn), baseline=baseline, r2i=r2i,
                comparison=comparison, insights=insights)


def scenario_to_dict(scn: Scenario) -> dict:
    return dict(
        name=scn.name, meta=scn.meta,
        hub=dict(lat=scn.hub.lat, lon=scn.hub.lon),
        orders=[dict(id=o.id, lat=o.lat, lon=o.lon, weight_kg=o.weight_kg,
                     tw_start_s=o.tw_start_s, tw_end_s=o.tw_end_s) for o in scn.orders],
        vehicles=[dict(id=v.id, spec_key=v.spec.key, label=v.spec.label, fuel=v.spec.fuel,
                       capacity_kg=v.spec.capacity_kg, shift_start_s=v.shift_start_s,
                       shift_end_s=v.shift_end_s) for v in scn.vehicles],
    )
