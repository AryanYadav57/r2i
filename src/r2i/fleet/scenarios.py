"""fleet/scenarios.py - Seeded synthetic scenarios and the curated preset."""

from __future__ import annotations

import math
import random

import numpy as np

from r2i.fleet.model import FleetVehicle, Hub, Order, Scenario
from r2i.fleet.network import RoadNetwork

# Koramangala 5th Block area (inside the cached graph)
PRESET_HUB = (12.9352, 77.6245)
PRESET_FLEET = ["van_diesel", "van_diesel", "2w_petrol", "2w_petrol", "3w_ev", "3w_ev", "van_ev"]

SLOTS = [(9, 11), (10, 12), (11, 13), (9, 13)]   # morning delivery windows, hours


def generate_scenario(net: RoadNetwork, n_orders: int = 30, seed: int = 42,
                      hub_lat: float = PRESET_HUB[0], hub_lon: float = PRESET_HUB[1],
                      fleet: list | None = None, radius_m: float = 3000.0,
                      name: str = "custom", shift_end_h: int = 13) -> Scenario:
    """Sample orders from graph nodes within radius_m of the hub (seeded)."""
    rng = random.Random(seed)
    hub_node = net.nearest(hub_lat, hub_lon)
    hlat, hlon = net.coords(hub_node)
    k = math.cos(math.radians(hlat))
    d_m = np.hypot(net.lat - hlat, (net.lon - hlon) * k) * 111_000
    candidates = [int(i) for i in np.flatnonzero((d_m <= radius_m) & (d_m > 150))]
    reachable = set(candidates) & _reachable_both_ways(net, hub_node)
    candidates = sorted(reachable)
    nodes = rng.sample(candidates, min(n_orders, len(candidates)))

    orders = []
    for i, node in enumerate(nodes):
        lo, hi = rng.choice(SLOTS)
        weight = round(min(60.0, rng.lognormvariate(2.0, 0.7)), 1)
        lat, lon = net.coords(node)
        orders.append(Order(f"O{i + 1:02d}", lat, lon, node, max(0.5, weight),
                            lo * 3600, hi * 3600))
    fleet = fleet or PRESET_FLEET
    counts: dict = {}
    vehicles = []
    for key in fleet:
        counts[key] = counts.get(key, 0) + 1
        vehicles.append(FleetVehicle.of(f"{_short(key)}-{counts[key]}", key,
                                        shift_end_s=shift_end_h * 3600))
    return Scenario(Hub(hlat, hlon, hub_node), orders, vehicles, name,
                    {"seed": seed, "radius_m": radius_m})


def preset_scenario(net: RoadNetwork) -> Scenario:
    return generate_scenario(net, 70, 42, name="koramangala-dark-store")


def _short(key: str) -> str:
    return {"van_diesel": "Van", "van_ev": "eVan", "2w_petrol": "Bike",
            "3w_ev": "e3W", "car_petrol": "Car", "car_ev": "eCar"}.get(key, key)


def _reachable_both_ways(net: RoadNetwork, hub: int) -> set:
    fwd, _ = net.dijkstra([hub], "distance")
    ok = set(np.flatnonzero(np.isfinite(fwd[0])).tolist())
    # reverse reachability: run from each candidate is costly; use transpose graph
    from scipy.sparse.csgraph import dijkstra
    back = dijkstra(net._csr("distance").T, indices=[hub])
    return ok & set(np.flatnonzero(np.isfinite(back[0])).tolist())
