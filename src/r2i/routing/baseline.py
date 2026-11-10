"""
routing/baseline.py - Standard Shortest-Path Router (Control Group)
Route-to-Impact (R2I) - Phase 3 Deliverable

This is the CONTROL GROUP. Every R2I improvement claim is a delta measured
against this baseline. Do not introduce any eco-cost logic here.

Algorithm: Dijkstra on edge 'length' attribute (distance-optimised).

Exit Condition (Phase 3):
  - Outputs deterministic trip metrics: distance (km), travel time (min),
    node count, intersection count.
  - Reproducible across runs (same OD pair -> same path).
  - test_routing.py Phase 3 tests all pass.
"""

import logging
import networkx as nx

logger = logging.getLogger(__name__)

# Minimum degree to count a node as a real intersection
INTERSECTION_MIN_DEGREE: int = 3


class RouteNotFoundError(Exception):
    """Raised when no valid path exists between an origin-destination pair."""
    pass


def shortest_path(G: nx.MultiDiGraph,
                  origin_node: int,
                  dest_node: int) -> tuple:
    """
    Compute the standard shortest-path (distance-optimised) between two nodes.

    Uses Dijkstra's algorithm on the 'length' edge attribute.
    Multi-edges are handled by taking the minimum-length parallel edge
    (NetworkX default for weight= in MultiDiGraph).

    Args:
        G:           NetworkX MultiDiGraph with 'length' edge attributes.
        origin_node: OSM node ID of the origin.
        dest_node:   OSM node ID of the destination.

    Returns:
        Tuple of (path: list[int], metrics: dict)
        where path is an ordered list of OSM node IDs and metrics contains:
          - distance_km        (float)
          - travel_time_min    (float)
          - node_count         (int)
          - intersection_count (int)

    Raises:
        RouteNotFoundError: If no path exists between origin and dest.
    """
    # Origin == destination: trivial single-node path
    if origin_node == dest_node:
        return [origin_node], _zero_metrics(origin_node)

    try:
        path = nx.shortest_path(G, origin_node, dest_node, weight="length")
    except nx.NetworkXNoPath:
        raise RouteNotFoundError(
            f"No path from node {origin_node} to node {dest_node}"
        )
    except nx.NodeNotFound as exc:
        raise RouteNotFoundError(str(exc))

    metrics = compute_path_metrics(G, path)
    logger.debug(
        "Baseline: %d -> %d | dist=%.2f km | t=%.1f min | nodes=%d | intersections=%d",
        origin_node, dest_node,
        metrics["distance_km"], metrics["travel_time_min"],
        metrics["node_count"], metrics["intersection_count"],
    )
    return path, metrics


def compute_path_metrics(G: nx.MultiDiGraph, path: list) -> dict:
    """
    Compute summary metrics for a given path.

    Args:
        G:    NetworkX MultiDiGraph.
        path: Ordered list of OSM node IDs.

    Returns:
        dict with keys:
          distance_km, travel_time_min, node_count, intersection_count
    """
    if len(path) <= 1:
        return _zero_metrics(path[0] if path else None)

    dist_m   = total_edge_length(G, path)
    time_s   = total_travel_time(G, path)
    n_isect  = count_intersections(G, path)

    return {
        "distance_km":        dist_m / 1000.0,
        "travel_time_min":    time_s / 60.0,
        "node_count":         len(path),
        "intersection_count": n_isect,
    }


def total_edge_length(G: nx.MultiDiGraph, path: list) -> float:
    """
    Sum 'length' attribute (metres) across all edges in the path.

    For multi-edges between consecutive nodes, picks the minimum-length
    parallel edge (consistent with Dijkstra's weight='length' choice).
    """
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        total += _min_edge_attr(G, u, v, "length", default=50.0)
    return total


def total_travel_time(G: nx.MultiDiGraph, path: list) -> float:
    """
    Sum 'travel_time' attribute (seconds) across all edges in the path.

    For multi-edges, picks the edge with minimum travel_time.
    """
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        total += _min_edge_attr(G, u, v, "travel_time", default=6.0)
    return total


def count_intersections(G: nx.MultiDiGraph, path: list) -> int:
    """
    Count intermediate nodes with degree >= INTERSECTION_MIN_DEGREE.

    Excludes origin and destination — only interior path nodes are checked.
    A degree >= 3 node has at least one branching option, making it a
    genuine decision point / intersection.
    """
    if len(path) < 3:
        return 0

    interior = path[1:-1]
    return sum(
        1 for node in interior
        if G.degree(node) >= INTERSECTION_MIN_DEGREE
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _min_edge_attr(G: nx.MultiDiGraph,
                   u: int,
                   v: int,
                   attr: str,
                   default: float) -> float:
    """
    Return the minimum value of `attr` across all parallel edges (u, v).
    Falls back to `default` if the attribute is missing.
    """
    edges = G[u][v]          # dict of {key: edge_data}
    vals  = [
        float(data.get(attr, default))
        for data in edges.values()
    ]
    return min(vals) if vals else default


def _zero_metrics(node) -> dict:
    """Return a zeroed metrics dict for trivial (same-node) paths."""
    return {
        "distance_km":        0.0,
        "travel_time_min":    0.0,
        "node_count":         1 if node is not None else 0,
        "intersection_count": 0,
    }
