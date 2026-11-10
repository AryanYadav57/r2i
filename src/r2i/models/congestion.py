"""
models/congestion.py - Structural Congestion Proxy Model
Route-to-Impact (R2I) - Phase 4 Deliverable

Implements FR4: Deterministic idle estimation without live API dependency.

Congestion Score Formula:
  S(v) = clip( (k_v * w_d + I_signal * w_s + W_class * w_c) / max_possible, 0, 1 )

  where:
    k_v     = node_degree       (intersection complexity)
    I_signal = 1 if is_signal else 0
    W_class  = highway_class_weight in [0.1, 1.0]
    w_d      = DEGREE_WEIGHT    (from config)
    w_s      = SIGNAL_WEIGHT    (from config)
    w_c      = ROAD_CLASS_WEIGHT (from config)

  max_possible = MAX_DEGREE_NORMALISE * w_d + 1 * w_s + 1 * w_c
               = 8 * 0.5 + 0.3 + 0.2 = 4.5

Edge Idle Time:
  T_idle(e) = S(destination_node) * T_base_idle

Exit Condition (Phase 4):
  test_congestion.py passes with 100% rate.
"""

import logging
import networkx as nx
from r2i import config

logger = logging.getLogger(__name__)

# Normalisation constant: assumed maximum realistic node degree in urban networks.
# A node with degree >= MAX_DEGREE_NORMALISE saturates the degree component.
MAX_DEGREE_NORMALISE: int = 8


def compute_congestion_score(node_data: dict, cfg=config) -> float:
    """
    Compute normalised congestion score S(v) in [0.0, 1.0] for a single node.

    Higher score = more idling expected when vehicles traverse this node.

    Formula:
      raw   = k_v * w_d + I_signal * w_s + W_class * w_c
      norm  = raw / max_possible
      S(v)  = clip(norm, 0.0, 1.0)

    Args:
        node_data: dict of node attributes containing:
                   - 'node_degree'          (int)   - intersection complexity
                   - 'is_signal'            (bool)  - traffic signal present
                   - 'highway_class_weight' (float) - road tier weight [0.1, 1.0]
        cfg:       Config module with DEGREE_WEIGHT, SIGNAL_WEIGHT,
                   ROAD_CLASS_WEIGHT constants.

    Returns:
        float in [0.0, 1.0]
    """
    degree      = float(node_data.get("node_degree", 0))
    is_signal   = float(bool(node_data.get("is_signal", False)))
    road_weight = float(node_data.get("highway_class_weight", cfg.HIGHWAY_CLASS_DEFAULT))

    w_d = cfg.DEGREE_WEIGHT
    w_s = cfg.SIGNAL_WEIGHT
    w_c = cfg.ROAD_CLASS_WEIGHT

    # Clamp degree to normalisation ceiling before weighting
    degree_clamped = min(degree, MAX_DEGREE_NORMALISE)

    raw = degree_clamped * w_d + is_signal * w_s + road_weight * w_c

    # max_possible: degree fully saturated + signal present + highest road class (1.0)
    max_possible = MAX_DEGREE_NORMALISE * w_d + 1.0 * w_s + 1.0 * w_c

    if max_possible <= 0.0:
        return 0.0

    score = raw / max_possible

    # Hard clip to [0, 1] — guards against floating-point edge cases
    return float(max(0.0, min(1.0, score)))


def compute_idle_time(congestion_score: float, cfg=config) -> float:
    """
    Derive predicted idle time at a node from its congestion score.

    Formula:
      T_idle = congestion_score * T_base_idle

    Args:
        congestion_score: float in [0.0, 1.0] from compute_congestion_score()
        cfg: Config module with T_BASE_IDLE constant.

    Returns:
        Estimated idle seconds (float >= 0.0).
    """
    return congestion_score * cfg.T_BASE_IDLE


def apply_congestion_to_graph(G: nx.MultiDiGraph, cfg=config) -> nx.MultiDiGraph:
    """
    Compute and attach congestion scores and idle times to all nodes in graph G.

    Adds node attributes in-place:
      - 'congestion_score' (float in [0, 1])
      - 'idle_time_s'      (float, seconds)

    Requires that the graph has already had features extracted:
      node_degree, is_signal, highway_class_weight.

    Args:
        G:   NetworkX MultiDiGraph with node features already extracted.
        cfg: Config module.

    Returns:
        Same graph G with congestion attributes attached (in-place modification).
    """
    total_idle = 0.0
    signal_count = 0

    for node, data in G.nodes(data=True):
        score = compute_congestion_score(data, cfg)
        idle  = compute_idle_time(score, cfg)

        G.nodes[node]["congestion_score"] = score
        G.nodes[node]["idle_time_s"]      = idle

        total_idle += idle
        if data.get("is_signal"):
            signal_count += 1

    n = G.number_of_nodes()
    logger.info(
        "Congestion applied to %d nodes  |  mean_score=%.3f  mean_idle=%.1fs  signals=%d",
        n,
        sum(d["congestion_score"] for _, d in G.nodes(data=True)) / max(n, 1),
        total_idle / max(n, 1),
        signal_count,
    )
    return G
