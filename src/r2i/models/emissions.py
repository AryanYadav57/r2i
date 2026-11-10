"""
models/emissions.py — Emission Calculation Utilities
Route-to-Impact (R2I) · Supporting Module

Provides helper functions to convert fuel burn to CO2 equivalents
and compute trip-level emission summaries.

All constants sourced from config.py — never hardcoded here.
"""

from r2i import config


def fuel_ml_to_co2_g(fuel_ml: float) -> float:
    """
    Convert fuel consumed (mL) to CO2 emitted (g).

    Formula: CO2_g = (fuel_ml / 1000) * CO2_PER_LITRE_PETROL

    Args:
        fuel_ml: Fuel volume in millilitres.

    Returns:
        CO2 mass in grams.
    """
    return (fuel_ml / 1000.0) * config.CO2_PER_LITRE_PETROL


def idle_co2_from_time(idle_seconds: float) -> float:
    """
    Compute CO2 emitted during idle period for an ICE vehicle.

    Args:
        idle_seconds: Duration of stationary engine running (seconds).

    Returns:
        CO2 in grams.
    """
    return idle_seconds * config.ICE_IDLE_CO2_PER_SEC


def idle_fuel_from_time(idle_seconds: float) -> float:
    """
    Compute fuel consumed during idle period for an ICE vehicle.

    Args:
        idle_seconds: Duration of stationary engine running (seconds).

    Returns:
        Fuel in millilitres.
    """
    return idle_seconds * config.ICE_IDLE_ML_PER_SEC
