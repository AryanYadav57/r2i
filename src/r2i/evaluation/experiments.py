"""
evaluation/experiments.py — Sensitivity Analysis & Parameter Sweep
Route-to-Impact (R2I) · Phase 10 Deliverable

Perturbs model parameters across defined ranges to verify model robustness
and identify the optimal ALPHA time-preference parameter.

Exit Condition (Phase 10):
  - Documented sensitivity curves showing eco-routes maintain directional
    advantage across all parameter variations.
  - Optimal ALPHA value identified and updated in config.py.
"""

import logging
from typing import List

import pandas as pd
import networkx as nx

from r2i import config
from r2i.models.vehicle import VehicleModel
from r2i.evaluation.benchmark import run_monte_carlo

logger = logging.getLogger(__name__)

class PatchedConfig:
    def __init__(self, overrides):
        self._overrides = overrides
    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(config, name)

def sweep_t_base_idle(G: nx.MultiDiGraph,
                      vehicle: VehicleModel,
                      values: List[float] = None,
                      n_trips: int = 50) -> pd.DataFrame:
    """
    Sweep T_base_idle across multiple values and record benchmark results.
    """
    if values is None:
        values = [10.0, 15.0, 17.5, 20.0, 25.0, 30.0]

    results = []

    for t_idle in values:
        logger.info(f"Sweeping T_base_idle = {t_idle}")

        cfg = PatchedConfig({"T_BASE_IDLE": t_idle})
        df_trips = run_monte_carlo(G, vehicle, n_trips=n_trips, cfg=cfg)

        if not df_trips.empty:
            mean_fuel_saved = df_trips["fuel_saved_ml"].mean()
            mean_co2_avoided = df_trips["co2_avoided_g"].mean()
            mean_time_delta = df_trips["time_delta_s"].mean()
            divergence_rate = (df_trips["diverged"].sum() / len(df_trips)) * 100.0
        else:
            mean_fuel_saved, mean_co2_avoided, mean_time_delta, divergence_rate = 0.0, 0.0, 0.0, 0.0

        results.append({
            "t_base_idle": t_idle,
            "mean_fuel_saved": mean_fuel_saved,
            "mean_co2_avoided": mean_co2_avoided,
            "mean_time_delta": mean_time_delta,
            "divergence_rate": divergence_rate
        })

    return pd.DataFrame(results)

def sweep_alpha(G: nx.MultiDiGraph,
                vehicle: VehicleModel,
                values: List[float] = None,
                n_trips: int = 50) -> pd.DataFrame:
    """
    Sweep ALPHA (time-preference weight) and record divergence stability.
    """
    if values is None:
        values = [0.0, 0.5, 1.0, 2.0, 5.0]

    results = []

    for alpha in values:
        logger.info(f"Sweeping ALPHA = {alpha}")

        cfg = PatchedConfig({"ALPHA": alpha})
        df_trips = run_monte_carlo(G, vehicle, n_trips=n_trips, cfg=cfg)

        if not df_trips.empty:
            mean_time_delta = df_trips["time_delta_s"].mean()
            divergence_rate = (df_trips["diverged"].sum() / len(df_trips)) * 100.0
            mean_fuel_saved = df_trips["fuel_saved_ml"].mean()
        else:
            mean_time_delta, divergence_rate, mean_fuel_saved = 0.0, 0.0, 0.0

        results.append({
            "alpha": alpha,
            "divergence_rate": divergence_rate,
            "mean_time_delta": mean_time_delta,
            "mean_fuel_saved": mean_fuel_saved
        })

    return pd.DataFrame(results)
