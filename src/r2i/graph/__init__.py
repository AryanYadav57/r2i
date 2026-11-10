"""
r2i.graph - Geospatial Data Pipeline
Route-to-Impact (R2I)

Public API:
  load_graph()          - Download or load cached OSM graph
  clean_graph()         - Remove self-loops, extract SCC, impute attributes
  extract_all_features()- Attach node_degree, is_signal, highway_class_weight
  validate_graph()      - Assert graph quality invariants
  graph_summary()       - Return lightweight stats dict
"""

from r2i.graph.loader import load_graph, graph_summary
from r2i.graph.preprocessing import (
    clean_graph,
    remove_self_loops,
    extract_largest_component,
    impute_missing_attributes,
    validate_graph,
)
from r2i.graph.features import (
    extract_all_features,
    compute_node_degrees,
    extract_signal_tags,
    map_highway_class_weights,
    get_highway_weight,
)

__all__ = [
    "load_graph",
    "graph_summary",
    "clean_graph",
    "remove_self_loops",
    "extract_largest_component",
    "impute_missing_attributes",
    "validate_graph",
    "extract_all_features",
    "compute_node_degrees",
    "extract_signal_tags",
    "map_highway_class_weights",
    "get_highway_weight",
]
