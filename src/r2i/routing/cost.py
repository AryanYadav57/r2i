"""
routing/cost.py - Environmental Edge Weight Function
Route-to-Impact (R2I) - Phase 6 Deliverable

Core formula (applied to every edge before Dijkstra routing):

  W_edge(e) = E_cruise(e) + E_idle(e) + alpha * T_travel(e)

  Where:
    E_cruise(e)  = L_e_km * vehicle.cruise_cost(1.0)
                 = edge_length_km * g_CO2_per_km
                 [g CO2 from driving the road segment at constant speed]

    E_idle(e)    = T_idle(dest_node) * vehicle.idle_cost(1.0)
                 = S(dest) * T_base_idle * g_CO2_per_second
                 [g CO2 from predicted idling at the destination intersection]

    alpha * T_travel(e) = cfg.ALPHA * travel_time_seconds
                 [time preference penalty — higher alpha prefers faster routes]

  Design:
    - No vehicle type checks (if/isinstance) in this file.
    - All vehicle physics delegated to VehicleModel.cruise_cost / .idle_cost.
    - Congestion model delegated to compute_congestion_score / compute_idle_time.
    - alpha = 0.0 => pure emission minimisation (ignores travel time).
    - alpha >> 1 => time-optimised (approaches shortest-time routing).

Exit Condition (Phase 6):
  - Standalone unit tests pass across all synthetic edge scenarios.
  - Monotonicity: increasing length -> increasing weight.
  - All edge weights are positive finite numbers (no NaN, no inf, no negative).
  - ICE weight > EV weight on congested node (divergence invariant).
"""

import logging
import math
import networkx as nx

from r2i import config
from r2i.models.vehicle import VehicleModel
from r2i.models.congestion import compute_congestion_score, compute_idle_time

logger = logging.getLogger(__name__)


def compute_edge_weight(edge_data: dict,
                        dest_node_data: dict,
                        vehicle: VehicleModel,
                        cfg=config) -> float:
    """
    Compute R2I environmental edge weight for a single road segment.

    Formula:
      W = E_cruise + E_idle + alpha * T_travel

    Args:
        edge_data:      dict with keys: length (m), travel_time (s), speed_kph
        dest_node_data: dict with node features for congestion scoring
                        (node_degree, is_signal, highway_class_weight)
        vehicle:        VehicleModel — cruise_cost and idle_cost called here
        cfg:            Config module with ALPHA and T_BASE_IDLE constants.

    Returns:
        Scalar edge weight >= 0. Units: g CO2-equivalent (with time penalty).

    Raises:
        ValueError: If computed weight is NaN or infinite.
    """
    # --- 1. Cruise emission component ---
    length_m  = float(edge_data.get("length", 50.0))
    length_km = length_m / 1000.0
    e_cruise  = vehicle.cruise_cost(length_km)

    # --- 2. Idle emission component ---
    # Congestion at the destination node determines predicted idle time
    congestion  = compute_congestion_score(dest_node_data, cfg)
    idle_time_s = compute_idle_time(congestion, cfg)
    e_idle      = vehicle.idle_cost(idle_time_s)

    # --- 3. Time preference penalty ---
    travel_time_s = float(edge_data.get("travel_time", 0.0))
    time_penalty  = cfg.ALPHA * travel_time_s

    weight = e_cruise + e_idle + time_penalty

    # Guard: no NaN / inf allowed in Dijkstra weight
    if not math.isfinite(weight):
        raise ValueError(
            f"Non-finite edge weight {weight} for "
            f"edge={edge_data!r}  dest_node={dest_node_data!r}  vehicle={vehicle.name}"
        )

    # Guard: weights must be non-negative for Dijkstra correctness
    if weight < 0.0:
        logger.warning(
            "Negative edge weight %.4f clamped to 0.0 "
            "(vehicle=%s  length_km=%.3f  idle_s=%.2f)",
            weight, vehicle.name, length_km, idle_time_s
        )
        weight = 0.0

    return weight


def compute_edge_weight_breakdown(edge_data: dict,
                                  dest_node_data: dict,
                                  vehicle: VehicleModel,
                                  cfg=config) -> dict:
    """
    Same as compute_edge_weight() but returns all components individually.

    Useful for route explanation (Dashboard Panel D) and benchmarking.

    Returns:
        dict with keys:
          cruise_co2_g    - g CO2 from cruising
          idle_co2_g      - g CO2 from idling at destination
          time_penalty    - alpha * travel_time_s
          congestion_score- S(dest_node)
          idle_time_s     - predicted idle seconds
          total_weight    - W_edge (sum of above three)
          fuel_ml         - total fuel, cruise + idle (mL; 0 for EV)
          idle_fuel_ml    - fuel burned idling (mL)
          energy_kwh      - traction energy (kWh; EV only)
          co2_g           - tailpipe CO2 = cruise_co2_g + idle_co2_g
    """
    length_m    = float(edge_data.get("length", 50.0))
    length_km   = length_m / 1000.0
    travel_s    = float(edge_data.get("travel_time", 0.0))

    congestion  = compute_congestion_score(dest_node_data, cfg)
    idle_s      = compute_idle_time(congestion, cfg)

    cruise_co2  = vehicle.cruise_cost(length_km)
    idle_co2    = vehicle.idle_cost(idle_s)
    time_pen    = cfg.ALPHA * travel_s
    idle_fuel   = vehicle.idle_fuel(idle_s)
    fuel_ml     = vehicle.fuel_ml(length_km, idle_s)
    energy_kwh  = vehicle.energy_kwh(length_km)

    total = cruise_co2 + idle_co2 + time_pen
    total = max(0.0, total)

    return {
        "cruise_co2_g":     cruise_co2,
        "idle_co2_g":       idle_co2,
        "time_penalty":     time_pen,
        "congestion_score": congestion,
        "idle_time_s":      idle_s,
        "total_weight":     total,
        "fuel_ml":          fuel_ml,
        "idle_fuel_ml":     idle_fuel,
        "energy_kwh":       energy_kwh,
        "co2_g":            cruise_co2 + idle_co2,
        "length_km":        length_km,
        "travel_time_s":    travel_s,
    }


def apply_weights_to_graph(G: nx.MultiDiGraph,
                           vehicle: VehicleModel,
                           cfg=config) -> nx.MultiDiGraph:
    """
    Pre-compute R2I weights for all edges and attach as 'r2i_weight' attribute.

    Must be called AFTER:
      1. graph.preprocessing.clean_graph()
      2. graph.features.extract_all_features()
      3. models.congestion.apply_congestion_to_graph()  (for congestion_score node attr)

    After this call, eco_route() uses 'r2i_weight' as the Dijkstra weight.

    Args:
        G:       NetworkX MultiDiGraph with node features and congestion scores.
        vehicle: VehicleModel instance (ICEVehicle or EVVehicle).
        cfg:     Config module.

    Returns:
        Same graph G with 'r2i_weight' on every edge (in-place).
    """
    n_edges  = 0
    total_w  = 0.0
    max_w    = 0.0

    for u, v, key, edge_data in G.edges(keys=True, data=True):
        dest_node_data = dict(G.nodes[v])
        weight = compute_edge_weight(edge_data, dest_node_data, vehicle, cfg)
        G[u][v][key]["r2i_weight"] = weight
        n_edges += 1
        total_w += weight
        max_w    = max(max_w, weight)

    logger.info(
        "R2I weights applied to %d edges  |  vehicle=%s  mean=%.2f  max=%.2f",
        n_edges, vehicle.name,
        total_w / max(n_edges, 1),
        max_w,
    )
    return G
