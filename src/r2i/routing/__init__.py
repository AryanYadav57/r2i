"""
r2i.routing - Routing Engine
Route-to-Impact (R2I)

Public API:
  shortest_path()            - Baseline distance-optimised Dijkstra
  compute_path_metrics()     - Metrics for any given path
  RouteNotFoundError         - Raised on unreachable OD pairs
  compute_edge_weight()      - W_edge formula (Phase 6)
  compute_edge_weight_breakdown() - Per-component breakdown
  apply_weights_to_graph()   - Stamp r2i_weight on all edges
  (Phase 7) eco_route(), compare_routes()
"""

from r2i.routing.baseline import (
    shortest_path,
    compute_path_metrics,
    total_edge_length,
    total_travel_time,
    count_intersections,
    RouteNotFoundError,
)
from r2i.routing.cost import (
    compute_edge_weight,
    compute_edge_weight_breakdown,
    apply_weights_to_graph,
)

__all__ = [
    "shortest_path",
    "compute_path_metrics",
    "total_edge_length",
    "total_travel_time",
    "count_intersections",
    "RouteNotFoundError",
    "compute_edge_weight",
    "compute_edge_weight_breakdown",
    "apply_weights_to_graph",
]
