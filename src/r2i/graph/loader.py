"""
graph/loader.py - OSM Graph Loader & Cache Manager
Route-to-Impact (R2I) - Phase 2 Deliverable

Responsibilities:
  - Download the Koramangala drive network from OpenStreetMap via osmnx
  - Cache the graph to disk as GraphML so subsequent runs are instant
  - Expose a single load_graph() entrypoint consumed by all other modules

Exit Condition (Phase 2):
  Graph loads from cache in < 2 seconds on second call.
  Graph has > 500 nodes covering the Koramangala bounding box.
"""

import logging
import os
import time

import networkx as nx
import osmnx as ox

from r2i import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# osmnx global settings
# ---------------------------------------------------------------------------
ox.settings.log_console = False
ox.settings.use_cache = True


def load_graph(cache_path: str = config.GRAPH_CACHE_PATH,
               force_download: bool = False) -> nx.MultiDiGraph:
    """
    Load the Koramangala road network.

    Strategy:
      1. If cache_path exists and force_download is False, load from disk.
      2. Otherwise, download from OSM and save to cache_path.

    Args:
        cache_path:      Path to the cached GraphML file.
        force_download:  If True, skip the cache and re-download from OSM.

    Returns:
        Raw MultiDiGraph (not yet preprocessed or feature-enriched).
    """
    if not force_download and os.path.exists(cache_path):
        logger.info("Loading graph from cache: %s", cache_path)
        t0 = time.perf_counter()
        G = ox.load_graphml(cache_path)
        elapsed = time.perf_counter() - t0
        logger.info("Cache load completed in %.2fs  |  nodes=%d  edges=%d",
                    elapsed, G.number_of_nodes(), G.number_of_edges())
        return G

    logger.info("Downloading OSM network for %s, %s ...",
                config.DEFAULT_DISTRICT, config.DEFAULT_CITY)
    G = _download_graph()
    _save_graph(G, cache_path)
    return G


def _download_graph() -> nx.MultiDiGraph:
    """
    Download the drive network for Koramangala, Bengaluru from OSM.

    Uses the place-name query so the bounding polygon comes from Nominatim,
    which is more reliable than a fixed bounding box for local deployments.

    Falls back to a bounding-box query if the place query fails.
    """
    query = f"{config.DEFAULT_DISTRICT}, {config.DEFAULT_CITY}, India"
    try:
        logger.info("Trying place query: '%s'", query)
        G = ox.graph_from_place(query, network_type=config.OSM_NETWORK_TYPE)
        logger.info("Place query succeeded  |  nodes=%d  edges=%d",
                    G.number_of_nodes(), G.number_of_edges())
        return G
    except Exception as exc:
        logger.warning("Place query failed (%s). Falling back to bbox.", exc)

    # Fallback: tight bounding box around Koramangala core (~2.5 km radius)
    # Verified correct: N=12.945 S=12.925 E=77.635 W=77.610
    north, south, east, west = 12.945, 12.925, 77.635, 77.610
    logger.info("Using bbox fallback: N=%.3f S=%.3f E=%.3f W=%.3f",
                north, south, east, west)
    G = ox.graph_from_bbox(
        bbox=(north, south, east, west),
        network_type=config.OSM_NETWORK_TYPE,
    )
    logger.info("BBox query succeeded  |  nodes=%d  edges=%d",
                G.number_of_nodes(), G.number_of_edges())
    return G


def _save_graph(G: nx.MultiDiGraph, cache_path: str) -> None:
    """Persist the graph to disk as GraphML, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    ox.save_graphml(G, cache_path)
    logger.info("Graph saved to %s", cache_path)


def graph_summary(G: nx.MultiDiGraph) -> dict:
    """
    Return a lightweight summary dict for logging and validation.

    Returns:
        dict with keys: nodes, edges, is_strongly_connected,
        has_self_loops, crs.
    """
    return {
        "nodes":                  G.number_of_nodes(),
        "edges":                  G.number_of_edges(),
        "is_strongly_connected":  nx.is_strongly_connected(G),
        "has_self_loops":         nx.number_of_selfloops(G) > 0,
        "crs":                    G.graph.get("crs", "unknown"),
    }
