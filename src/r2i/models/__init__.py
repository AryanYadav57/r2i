"""
r2i.models - Vehicle & Environmental Models
Route-to-Impact (R2I)

Public API:
  VehicleModel              - ABC defining cruise_cost / idle_cost / idle_fuel
  ICEVehicle                - 1.5L petrol engine cost model
  EVVehicle                 - Zero tailpipe EV cost model
  make_vehicle()            - Factory: 'ICE' | 'EV' -> VehicleModel instance
  compute_congestion_score()- S(v): node congestion in [0,1]
  compute_idle_time()       - T_idle = S(v) * T_base_idle
  apply_congestion_to_graph()- Attach scores/idle to all graph nodes
  fuel_ml_to_co2_g()        - Fuel volume -> CO2 mass
  idle_co2_from_time()      - Idle seconds -> CO2 grams (ICE)
  idle_fuel_from_time()     - Idle seconds -> fuel mL (ICE)
"""

from r2i.models.vehicle import VehicleModel, ICEVehicle, EVVehicle, make_vehicle
from r2i.models.congestion import (
    compute_congestion_score,
    compute_idle_time,
    apply_congestion_to_graph,
    MAX_DEGREE_NORMALISE,
)
from r2i.models.emissions import (
    fuel_ml_to_co2_g,
    idle_co2_from_time,
    idle_fuel_from_time,
)

__all__ = [
    "VehicleModel",
    "ICEVehicle",
    "EVVehicle",
    "make_vehicle",
    "compute_congestion_score",
    "compute_idle_time",
    "apply_congestion_to_graph",
    "MAX_DEGREE_NORMALISE",
    "fuel_ml_to_co2_g",
    "idle_co2_from_time",
    "idle_fuel_from_time",
]
