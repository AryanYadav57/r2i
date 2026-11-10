"""
routing/router.py - R2I Eco-Router Integration
Route-to-Impact (R2I) -- Phase 7 Deliverable

Integrates graph features, vehicle dynamics, and cost functions into a unified
eco-router that finds minimum environmental impact paths.

Key Design:
  - eco_route()           - R2I optimised path via 'r2i_weight'
  - compute_eco_metrics() - Per-path emission and fuel accounting
  - compare_routes()      - Side-by-side baseline vs. R2I comparison (used by UI)

Formula:
  W_edge = E_cruise + E_idle + alpha * T_travel

  eco_route() minimises sum(W_edge) over all edges in the path.
  baseline shortest_path() minimises sum(length) -- pure distance.

Exit Condition (Phase 7):
  - Router outputs an eco-route that diverges from baseline on >= 1 high-congestion test case.
  - origin==dest returns graceful empty result.
  - Disconnected pair raises RouteNotFoundError (not raw NetworkX exception).

CLI Usage:
  python -m r2i.routing.router --origin "12.9352,77.6245" --dest "12.9716,77.5946" --vehicle ICE
"""

import argparse
import logging

import networkx as nx

from r2i import config
from r2i.models.vehicle import VehicleModel
from r2i.routing.baseline import (
    shortest_path,
    RouteNotFoundError,
)
from r2i.routing.cost import apply_weights_to_graph, compute_edge_weight_breakdown

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primary API
# ---------------------------------------------------------------------------

def eco_route(G: nx.MultiDiGraph,
              origin_node: int,
              dest_node: int,
              vehicle: VehicleModel,
              cfg=config) -> tuple:
    """
    Compute the R2I eco-optimised route between two OSM nodes.

    Pre-computes 'r2i_weight' on every graph edge, then runs Dijkstra
    to find the minimum environmental cost path.

    Args:
        G:           MultiDiGraph with all features and congestion scores pre-computed.
                     Requires node attributes: node_degree, is_signal,
                     highway_class_weight (or congestion_score + idle_time_s).
        origin_node: OSM node ID of the origin.
        dest_node:   OSM node ID of the destination.
        vehicle:     VehicleModel instance (ICEVehicle or EVVehicle).
        cfg:         Config module with ALPHA, T_BASE_IDLE etc.

    Returns:
        Tuple of (eco_path: list[int], eco_metrics: dict)
        eco_metrics keys:
          distance_km, travel_time_s, travel_time_min,
          total_idle_s, total_co2_g, fuel_ml, node_count

    Raises:
        RouteNotFoundError: If no path exists between origin and dest.
    """
    # Degenerate case: same origin and destination
    if origin_node == dest_node:
        return [origin_node], _zero_eco_metrics(origin_node)

    # Stamp r2i_weight on every edge (in-place, non-destructive to other attrs)
    apply_weights_to_graph(G, vehicle, cfg)

    try:
        path = nx.shortest_path(G, origin_node, dest_node, weight="r2i_weight")
    except nx.NetworkXNoPath:
        raise RouteNotFoundError(
            f"No eco-route from node {origin_node} to node {dest_node}"
        )
    except nx.NodeNotFound as exc:
        raise RouteNotFoundError(str(exc))

    metrics = compute_eco_metrics(G, path, vehicle)

    logger.debug(
        "Eco-route: %d -> %d | dist=%.2f km | idle=%.1fs | co2=%.1fg | nodes=%d",
        origin_node, dest_node,
        metrics["distance_km"], metrics["total_idle_s"],
        metrics["total_co2_g"], metrics["node_count"],
    )
    return path, metrics


def compute_eco_metrics(G: nx.MultiDiGraph,
                        path: list,
                        vehicle: VehicleModel) -> dict:
    """
    Compute eco-specific metrics for an R2I or any given path.

    Walks every consecutive (u, v) edge pair and accumulates emission
    and fuel figures using the vehicle's physics model.

    Args:
        G:       NetworkX MultiDiGraph with 'r2i_weight' and node features.
        path:    Ordered list of OSM node IDs.
        vehicle: VehicleModel instance.

    Returns:
        dict with keys:
          distance_km      - total path length in kilometres
          travel_time_s    - total travel time in seconds
          travel_time_min  - total travel time in minutes
          total_idle_s     - predicted total idle time in seconds
          total_co2_g      - tailpipe CO2 (cruise + idle), grams
          fuel_ml          - total fuel (cruise + idle), mL; 0 for EV
          energy_kwh       - traction energy, kWh (EV only)
          grid_co2_g       - upstream grid CO2 for energy_kwh
          cost_inr         - energy cost in INR
          routing_cost     - sum of W_edge (includes alpha * time)
          node_count       - number of nodes in path
    """
    if len(path) <= 1:
        return _zero_eco_metrics(path[0] if path else None)

    dist_m = travel_s = idle_s = co2_g = fuel_ml = kwh = cost = 0.0

    for u, v in zip(path[:-1], path[1:]):
        # Pick the min-weight parallel edge (consistent with Dijkstra's choice)
        edge_data      = _best_edge_data(G, u, v)
        dest_node_data = dict(G.nodes[v])

        bd = compute_edge_weight_breakdown(edge_data, dest_node_data, vehicle)

        dist_m   += float(edge_data.get("length", 50.0))
        travel_s += bd["travel_time_s"]
        idle_s   += bd["idle_time_s"]
        co2_g    += bd["co2_g"]          # tailpipe CO2 only (no time penalty)
        fuel_ml  += bd["fuel_ml"]
        kwh      += bd["energy_kwh"]
        cost     += bd["total_weight"]   # routing objective incl. alpha * time

    return {
        "distance_km":     dist_m / 1000.0,
        "travel_time_s":   travel_s,
        "travel_time_min": travel_s / 60.0,
        "total_idle_s":    idle_s,
        "total_co2_g":     co2_g,
        "fuel_ml":         fuel_ml,
        "energy_kwh":      kwh,
        "grid_co2_g":      kwh * config.GRID_CO2_G_PER_KWH,
        "cost_inr":        vehicle.energy_cost_inr(fuel_ml, kwh),
        "routing_cost":    cost,
        "node_count":      len(path),
    }


def compare_routes(G: nx.MultiDiGraph,
                   origin_node: int,
                   dest_node: int,
                   vehicle: VehicleModel,
                   cfg=config) -> dict:
    """
    Compute and compare baseline vs. R2I routes for the same OD pair.

    This is the primary function called by the Streamlit dashboard and
    the benchmark engine (Phase 9).

    Args:
        G:           MultiDiGraph with all features and congestion scores.
        origin_node: OSM node ID of the origin.
        dest_node:   OSM node ID of the destination.
        vehicle:     VehicleModel instance.
        cfg:         Config module.

    Returns:
        dict with keys:
          baseline_path   - list[int] of OSM node IDs (shortest distance)
          r2i_path        - list[int] of OSM node IDs (eco-optimised)
          baseline        - dict of baseline path eco-metrics
          r2i             - dict of R2I path eco-metrics
          diverged        - bool, True if paths differ
          avoided_nodes   - list[int] of high-congestion node IDs that the
                            baseline uses but R2I avoids (for Panel D)
          delta           - dict of (r2i - baseline) differences per metric

    Raises:
        RouteNotFoundError: If either route cannot be computed.
    """
    # --- Baseline route (distance-optimised) ---
    baseline_path, _baseline_dist_metrics = shortest_path(G, origin_node, dest_node)

    # --- R2I eco route (emission-optimised) ---
    r2i_path, r2i_metrics = eco_route(G, origin_node, dest_node, vehicle, cfg)

    # --- Divergence ---
    diverged = (baseline_path != r2i_path)

    # --- Nodes avoided: in baseline but not in r2i (excluding endpoints) ---
    r2i_set = set(r2i_path)
    avoided_nodes = [
        node for node in baseline_path
        if node not in r2i_set
        and node not in (origin_node, dest_node)
    ]

    # --- Compute eco metrics for the baseline path (fair delta comparison) ---
    baseline_eco = compute_eco_metrics(G, baseline_path, vehicle)

    # --- Delta: positive = R2I uses more; negative = R2I saves ---
    delta = {
        "distance_km":   r2i_metrics["distance_km"]   - baseline_eco["distance_km"],
        "travel_time_s": r2i_metrics["travel_time_s"] - baseline_eco["travel_time_s"],
        "total_idle_s":  r2i_metrics["total_idle_s"]  - baseline_eco["total_idle_s"],
        "total_co2_g":   r2i_metrics["total_co2_g"]   - baseline_eco["total_co2_g"],
        "fuel_ml":       r2i_metrics["fuel_ml"]       - baseline_eco["fuel_ml"],
        "energy_kwh":    r2i_metrics["energy_kwh"]    - baseline_eco["energy_kwh"],
        "cost_inr":      r2i_metrics["cost_inr"]      - baseline_eco["cost_inr"],
    }

    logger.info(
        "Compare %d->%d | diverged=%s | delta_dist=%.3fkm | delta_idle=%.1fs | delta_co2=%.1fg",
        origin_node, dest_node, diverged,
        delta["distance_km"], delta["total_idle_s"], delta["total_co2_g"],
    )

    return {
        "baseline_path":  baseline_path,
        "r2i_path":       r2i_path,
        "baseline":       baseline_eco,
        "r2i":            r2i_metrics,
        "diverged":       diverged,
        "avoided_nodes":  avoided_nodes,
        "delta":          delta,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _best_edge_data(G: nx.MultiDiGraph, u: int, v: int) -> dict:
    """
    Return edge data dict for the minimum-r2i_weight parallel edge (u, v).
    Falls back to minimum-length if r2i_weight is not yet stamped.
    """
    edges = G[u][v]   # {key: edge_data_dict}
    if not edges:
        return {}

    def sort_key(item):
        data = item[1]
        if "r2i_weight" in data:
            return data["r2i_weight"]
        return data.get("length", 50.0)

    best_key = min(edges.items(), key=sort_key)[0]
    return dict(edges[best_key])


def _zero_eco_metrics(node) -> dict:
    """Return zeroed eco metrics dict for trivial (same-node) paths."""
    keys = ("distance_km", "travel_time_s", "travel_time_min", "total_idle_s",
            "total_co2_g", "fuel_ml", "energy_kwh", "grid_co2_g", "cost_inr",
            "routing_cost")
    out = {k: 0.0 for k in keys}
    out["node_count"] = 1 if node is not None else 0
    return out


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="R2I Eco-Router CLI")
    parser.add_argument("--origin",  required=True, help="lat,lon e.g. 12.9352,77.6245")
    parser.add_argument("--dest",    required=True, help="lat,lon e.g. 12.9716,77.5946")
    parser.add_argument("--vehicle", default="ICE",
                        help="ICE, EV or a vehicle class key (e.g. van_diesel)")
    return parser.parse_args()


def load_routing_graph():
    """Load the cached OSM graph and run the full feature pipeline."""
    from r2i.graph.features import extract_all_features
    from r2i.graph.loader import load_graph
    from r2i.graph.preprocessing import clean_graph
    from r2i.models.congestion import apply_congestion_to_graph

    G = extract_all_features(clean_graph(load_graph()))
    apply_congestion_to_graph(G)
    return G


def main() -> None:
    import osmnx as ox

    from r2i.models.vehicle import make_vehicle

    logging.basicConfig(level=logging.WARNING)
    args = _parse_args()
    (olat, olon), (dlat, dlon) = (map(float, args.origin.split(",")),
                                  map(float, args.dest.split(",")))
    G = load_routing_graph()
    o = ox.nearest_nodes(G, olon, olat)
    d = ox.nearest_nodes(G, dlon, dlat)
    res = compare_routes(G, o, d, make_vehicle(args.vehicle))
    print(f"{'metric':<16}{'baseline':>12}{'r2i':>12}")
    for k in ("distance_km", "travel_time_min", "total_idle_s", "total_co2_g",
              "fuel_ml", "energy_kwh", "cost_inr"):
        print(f"{k:<16}{res['baseline'][k]:>12.2f}{res['r2i'][k]:>12.2f}")
    print(f"diverged: {res['diverged']}")


if __name__ == "__main__":
    main()
