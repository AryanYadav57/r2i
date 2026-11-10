"""
graph/preprocessing.py - Graph Cleaning & Structural Preprocessing
Route-to-Impact (R2I) - Phase 2 Deliverable

Responsibilities:
  - Remove self-loops
  - Ensure strong connectivity (keep largest strongly-connected component)
  - Impute missing speed/length attributes with sensible defaults
  - Verify all edges have required attributes: length, highway, travel_time

Exit Condition (Phase 2):
  test_graph.py passes: no self-loops, all edges have length and highway attributes.
"""

import logging
import networkx as nx

logger = logging.getLogger(__name__)

# Default speed (km/h) used when OSM speed tag is missing
DEFAULT_SPEED_KPH: float = 30.0
# Default edge length (m) fallback
DEFAULT_LENGTH_M: float = 50.0


def clean_graph(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Run the full preprocessing pipeline on a raw OSM graph.

    Pipeline:
      1. remove_self_loops(G)
      2. extract_largest_component(G)
      3. impute_missing_attributes(G)

    Args:
        G: Raw NetworkX MultiDiGraph from OSMnx

    Returns:
        Cleaned, strongly-connected MultiDiGraph
    """
    logger.info("Starting graph cleaning pipeline  |  nodes=%d  edges=%d",
                G.number_of_nodes(), G.number_of_edges())

    G = remove_self_loops(G)
    G = extract_largest_component(G)
    G = impute_missing_attributes(G)

    logger.info("Graph cleaning complete  |  nodes=%d  edges=%d",
                G.number_of_nodes(), G.number_of_edges())
    return G


def remove_self_loops(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Remove all self-loop edges (origin == destination node)."""
    self_loops = list(nx.selfloop_edges(G, keys=True))
    n = len(self_loops)
    if n:
        G.remove_edges_from(self_loops)
        logger.info("Removed %d self-loop(s)", n)
    else:
        logger.debug("No self-loops found")
    return G


def extract_largest_component(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Keep only the largest strongly-connected component.
    Guarantees that any origin-destination pair within the component
    has a valid directed path.
    """
    if nx.is_strongly_connected(G):
        logger.debug("Graph is already strongly connected — no SCC extraction needed")
        return G

    # Find largest SCC by node count
    sccs = list(nx.strongly_connected_components(G))
    largest = max(sccs, key=len)
    nodes_before = G.number_of_nodes()

    G = G.subgraph(largest).copy()

    logger.info(
        "Extracted largest SCC: kept %d / %d nodes (%.1f%%)",
        G.number_of_nodes(), nodes_before,
        100.0 * G.number_of_nodes() / nodes_before,
    )
    return G


def impute_missing_attributes(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Impute missing edge attributes with defaults:
      - length:       DEFAULT_LENGTH_M  (metres)
      - speed_kph:    DEFAULT_SPEED_KPH (km/h)
      - travel_time:  length / (speed_kph * 1000 / 3600)  (seconds)
      - highway:      'unclassified'

    Also normalises speed_kph: OSM sometimes stores it as a string or list.
    """
    patched = 0
    for u, v, key, data in G.edges(keys=True, data=True):
        changed = False

        # --- highway ---
        if "highway" not in data or data["highway"] is None:
            data["highway"] = "unclassified"
            changed = True
        elif isinstance(data["highway"], list):
            # OSM can return a list when multiple tags exist; take first
            data["highway"] = data["highway"][0]
            changed = True

        # --- length ---
        if "length" not in data or data["length"] is None:
            data["length"] = DEFAULT_LENGTH_M
            changed = True
        else:
            data["length"] = float(data["length"])

        # --- speed_kph ---
        raw_speed = data.get("speed_kph") or data.get("maxspeed")
        if raw_speed is None:
            data["speed_kph"] = DEFAULT_SPEED_KPH
            changed = True
        else:
            # Parse "50 mph" / "50" / ["30", "50"] safely
            if isinstance(raw_speed, list):
                raw_speed = raw_speed[0]
            try:
                # Strip non-numeric suffix (e.g. "50 mph")
                speed_val = float(str(raw_speed).split()[0])
                # Convert mph -> km/h if needed
                if "mph" in str(raw_speed):
                    speed_val *= 1.60934
                data["speed_kph"] = speed_val
            except (ValueError, AttributeError):
                data["speed_kph"] = DEFAULT_SPEED_KPH
                changed = True

        # --- travel_time ---
        speed_mps = data["speed_kph"] * 1000.0 / 3600.0
        data["travel_time"] = data["length"] / speed_mps if speed_mps > 0 else 0.0

        if changed:
            patched += 1

    logger.info("Imputed missing attributes on %d edge(s)", patched)
    return G


def validate_graph(G: nx.MultiDiGraph) -> bool:
    """
    Assert minimum graph quality invariants. Returns True if valid.

    Checks:
      - No self-loops
      - All edges have 'length' attribute
      - All edges have 'highway' attribute
      - Graph is strongly connected

    Raises:
        AssertionError if any invariant is violated (with a descriptive message).
    """
    # Self-loops
    n_loops = nx.number_of_selfloops(G)
    assert n_loops == 0, f"Graph has {n_loops} self-loop(s)"

    # Edge attributes
    missing_length  = []
    missing_highway = []
    for u, v, key, data in G.edges(keys=True, data=True):
        if "length" not in data or data["length"] is None:
            missing_length.append((u, v, key))
        if "highway" not in data or data["highway"] is None:
            missing_highway.append((u, v, key))

    assert not missing_length, \
        f"{len(missing_length)} edge(s) missing 'length': first={missing_length[0]}"
    assert not missing_highway, \
        f"{len(missing_highway)} edge(s) missing 'highway': first={missing_highway[0]}"

    # Strong connectivity
    assert nx.is_strongly_connected(G), \
        "Graph is not strongly connected after preprocessing"

    logger.info("validate_graph(): all invariants passed  |  nodes=%d  edges=%d",
                G.number_of_nodes(), G.number_of_edges())
    return True
