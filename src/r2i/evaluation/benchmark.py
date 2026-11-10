"""
evaluation/benchmark.py — Monte Carlo OD Pair Benchmark Runner
Route-to-Impact (R2I) · Phase 9 Deliverable

Generates empirical evidence for the pitch by running compare_routes()
across hundreds of randomly sampled origin-destination pairs.

Output CSV columns:
  origin, dest, baseline_dist_km, r2i_dist_km, baseline_time_s, r2i_time_s,
  baseline_idle_s, r2i_idle_s, fuel_saved_ml, co2_avoided_g, time_delta_s, diverged

Exit Condition (Phase 9):
  - Clean benchmark CSV generated for 100+ OD pairs.
  - Route divergence rate > 0%.
  - Statistical summary computed: mean, median, std for each metric.
"""

import random
import logging

import pandas as pd
import networkx as nx

from r2i import config
from r2i.models.vehicle import VehicleModel
from r2i.routing.baseline import RouteNotFoundError
from r2i.routing.router import compare_routes
from r2i.evaluation.metrics import results_to_dataframe

logger = logging.getLogger(__name__)


def run_monte_carlo(G: nx.MultiDiGraph,
                    vehicle: VehicleModel,
                    n_trips: int = config.BENCHMARK_N_TRIPS,
                    seed: int = config.BENCHMARK_SEED,
                    cfg=config) -> pd.DataFrame:
    """
    Run Monte Carlo benchmark across n_trips random OD pairs.

    Args:
        G:       Preprocessed and feature-enriched MultiDiGraph.
        vehicle: VehicleModel instance.
        n_trips: Number of OD pairs to sample.
        seed:    Random seed for reproducibility.
        cfg:     Config module.

    Returns:
        DataFrame with one row per successful trip comparison.
    """
    random.seed(seed)
    nodes = list(G.nodes())
    results = []

    for _ in range(n_trips):
        origin, dest = random.choices(nodes, k=2)
        if origin == dest:
            continue
        try:
            comparison = compare_routes(G, origin, dest, vehicle, cfg)
            results.append(comparison)
        except RouteNotFoundError:
            continue

    df = results_to_dataframe(results)
    return df


def save_benchmark_results(df: pd.DataFrame, path: str) -> None:
    """Save benchmark DataFrame to CSV."""
    df.to_csv(path, index=False)


def load_benchmark_results(path: str) -> pd.DataFrame:
    """Load benchmark DataFrame from CSV."""
    return pd.read_csv(path)
