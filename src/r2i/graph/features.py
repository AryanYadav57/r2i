"""
graph/features.py - Node & Edge Feature Extraction
Route-to-Impact (R2I) - Phase 2 Deliverable

Responsibilities:
  - Compute node_degree for each node from graph topology
  - Extract is_signal boolean (highway == traffic_signals OSM tag)
  - Map highway classification string to numeric congestion weight
  - Attach all features as node/edge attributes in-place

These features feed directly into congestion.py (Phase 4).
"""

import logging
import networkx as nx
from r2i import config

logger = logging.getLogger(__name__)


def extract_all_features(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Run all feature extraction on the graph in-place.

    Adds the following node attributes:
      - node_degree          (int)
      - is_signal            (bool)
      - highway_class_weight (float in [0.1, 1.0])

    Args:
        G: Cleaned NetworkX MultiDiGraph

    Returns:
        Same graph with node attributes attached.
    """
    compute_node_degrees(G)
    extract_signal_tags(G)
    map_highway_class_weights(G)
    logger.info(
        "Feature extraction complete  |  nodes=%d  "
        "signals=%d  mean_degree=%.1f",
        G.number_of_nodes(),
        sum(1 for _, d in G.nodes(data=True) if d.get("is_signal")),
        sum(d.get("node_degree", 0) for _, d in G.nodes(data=True))
        / max(G.number_of_nodes(), 1),
    )
    return G


def compute_node_degrees(G: nx.MultiDiGraph) -> None:
    """
    Set node attribute 'node_degree' = number of physical streets at the node.

    Uses OSMnx's 'street_count' when present; otherwise counts distinct
    neighbouring nodes. (G.degree on a MultiDiGraph counts in + out edges,
    so a two-way 3-way junction would wrongly score 6.)
    """
    for node, data in G.nodes(data=True):
        sc = data.get("street_count")
        if sc is not None:
            G.nodes[node]["node_degree"] = int(sc)
        else:
            nbrs = set(G.successors(node)) | set(G.predecessors(node))
            nbrs.discard(node)
            G.nodes[node]["node_degree"] = len(nbrs)


def extract_signal_tags(G: nx.MultiDiGraph) -> None:
    """
    Set node attribute 'is_signal' = True if OSM tag highway == 'traffic_signals'.
    Traffic signals enforce stop-and-go cycles - major idle contributors.

    OSMnx stores node-level OSM tags directly as node attributes.
    The relevant tag is 'highway' with value 'traffic_signals'.
    """
    for node, data in G.nodes(data=True):
        highway_tag = data.get("highway", "")
        # OSM can store this as a string or a list
        if isinstance(highway_tag, list):
            is_sig = "traffic_signals" in highway_tag
        else:
            is_sig = highway_tag == "traffic_signals"
        G.nodes[node]["is_signal"] = is_sig


def map_highway_class_weights(G: nx.MultiDiGraph) -> None:
    """
    Set node attribute 'highway_class_weight' from the dominant adjacent highway type.

    Strategy:
      - Collect the highway types of all edges incident to this node
      - Pick the type with the HIGHEST congestion weight (worst case)
      - Fall back to HIGHWAY_CLASS_DEFAULT if no incident edges have highway tags

    Uses HIGHWAY_CLASS_WEIGHTS from config.py.
    """
    for node in G.nodes():
        # Collect all highway types on adjacent edges (in + out)
        highway_types = []
        for _, _, edge_data in G.in_edges(node, data=True):
            _collect_highway(edge_data, highway_types)
        for _, _, edge_data in G.out_edges(node, data=True):
            _collect_highway(edge_data, highway_types)

        if highway_types:
            # Take the maximum weight (most congested road type at this node)
            best_weight = max(
                config.HIGHWAY_CLASS_WEIGHTS.get(h, config.HIGHWAY_CLASS_DEFAULT)
                for h in highway_types
            )
        else:
            best_weight = config.HIGHWAY_CLASS_DEFAULT

        G.nodes[node]["highway_class_weight"] = best_weight


def get_highway_weight(highway_type: str) -> float:
    """
    Map a single highway type string to its numeric weight.

    Args:
        highway_type: OSM highway tag value (e.g., 'primary', 'residential')

    Returns:
        float weight from config.HIGHWAY_CLASS_WEIGHTS, or DEFAULT if not found.
    """
    return config.HIGHWAY_CLASS_WEIGHTS.get(highway_type, config.HIGHWAY_CLASS_DEFAULT)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_highway(edge_data: dict, out: list) -> None:
    """Extract highway string(s) from an edge data dict into `out`."""
    hw = edge_data.get("highway")
    if hw is None:
        return
    if isinstance(hw, list):
        out.extend(hw)
    else:
        out.append(hw)
