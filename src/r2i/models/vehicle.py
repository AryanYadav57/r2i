"""
models/vehicle.py - Physics-Based Vehicle Cost Abstractions
Route-to-Impact (R2I) - Phase 5 Deliverable

Design Rule:
  NO if/isinstance/type-switch on vehicle type anywhere in routing code.
  All vehicle-specific behaviour is isolated here via polymorphism.
  The router calls vehicle.cruise_cost() and vehicle.idle_cost() blindly —
  it never asks "what type of vehicle is this?"

Classes:
  VehicleModel  - Abstract base class defining the cost interface
  ICEVehicle    - Internal Combustion Engine: penalises cruise and idle CO2
  EVVehicle     - Electric Vehicle: zero point-of-use emissions

Exit Condition (Phase 5):
  Vehicle-specific cost models operate polymorphically.
  test_cost.py Phase 5 tests all pass.
  ICEVehicle.idle_cost(30) != EVVehicle.idle_cost(30)  (divergence invariant)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from r2i import config


class VehicleModel(ABC):
    """
    Abstract vehicle cost model.

    Every routing cost calculation MUST go through this interface.
    The engine is closed to modification but open to extension:
    adding a new vehicle type (e.g. HybridVehicle) requires ONLY
    subclassing VehicleModel — nothing else changes.
    """

    @abstractmethod
    def cruise_cost(self, distance_km: float) -> float:
        """
        Returns the environmental cost (g CO2) of cruising distance_km
        at the vehicle's characteristic emission rate.

        Args:
            distance_km: Road segment length in kilometres.

        Returns:
            g CO2 emitted while cruising this distance. Must be >= 0.
        """
        ...

    @abstractmethod
    def idle_cost(self, idle_seconds: float) -> float:
        """
        Returns the environmental cost (g CO2) of idling for idle_seconds.

        Args:
            idle_seconds: Predicted stationary engine-running time at a
                          node (seconds). Always >= 0.

        Returns:
            g CO2 emitted while idling. Must be >= 0.
        """
        ...

    @abstractmethod
    def idle_fuel(self, idle_seconds: float) -> float:
        """
        Returns the fuel consumed (mL) while idling for idle_seconds.
        Used by the benchmark to report fuel savings in mL.

        Args:
            idle_seconds: Stationary engine-running time (seconds).

        Returns:
            Fuel consumed in millilitres. Must be >= 0.
        """
        ...

    # --- v2 defaults (overridden by SpecVehicle) -------------------------
    def fuel_ml(self, distance_km: float, idle_seconds: float = 0.0) -> float:
        """Total fuel in mL (default: idle fuel only)."""
        return self.idle_fuel(idle_seconds)

    def energy_kwh(self, distance_km: float) -> float:
        """Traction energy in kWh (default: 0)."""
        return 0.0

    def energy_cost_inr(self, fuel_ml: float, energy_kwh: float) -> float:
        """Energy cost in INR (default: petrol price for fuel + tariff for kWh)."""
        return (fuel_ml / 1000.0 * config.FUEL_PRICE_INR_PER_L["petrol"]
                + energy_kwh * config.ELECTRICITY_INR_PER_KWH)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable vehicle type identifier (e.g. 'ICE', 'EV')."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


@dataclass(frozen=True)
class VehicleSpec:
    """
    Data-driven description of a vehicle class (all values are assumptions,
    documented in docs/assumptions.md, section "v2").

    fuel:             'petrol' | 'diesel' | 'electric'
    cruise_co2_g_km:  tailpipe CO2 when empty, g/km (0 for electric)
    idle_ml_s:        idle fuel draw, mL/s (0 for electric)
    kwh_per_km:       traction energy when empty (electric only)
    kerb_kg:          unladen mass
    capacity_kg:      maximum payload
    battery_kwh:      usable battery (electric only)
    """
    key: str
    label: str
    fuel: str
    cruise_co2_g_km: float
    idle_ml_s: float
    kwh_per_km: float
    kerb_kg: float
    capacity_kg: float
    battery_kwh: float = 0.0

    @property
    def is_electric(self) -> bool:
        return self.fuel == "electric"


VEHICLE_SPECS: dict = {
    "car_petrol": VehicleSpec("car_petrol", "Petrol car (1.5L)", "petrol",
                              config.ICE_CRUISE_CO2_PER_KM, config.ICE_IDLE_ML_PER_SEC,
                              0.0, 1100.0, 300.0),
    "car_ev":     VehicleSpec("car_ev", "Electric car", "electric",
                              0.0, 0.0, 0.15, 1500.0, 300.0, 40.0),
    "2w_petrol":  VehicleSpec("2w_petrol", "Petrol 2-wheeler", "petrol",
                              51.0, 0.05, 0.0, 110.0, 20.0),
    "3w_ev":      VehicleSpec("3w_ev", "Electric 3-wheeler cargo", "electric",
                              0.0, 0.0, 0.075, 400.0, 300.0, 8.0),
    "van_diesel": VehicleSpec("van_diesel", "Diesel mini-truck", "diesel",
                              179.0, 0.25, 0.0, 1000.0, 750.0),
    "van_ev":     VehicleSpec("van_ev", "Electric mini-truck", "electric",
                              0.0, 0.0, 0.14, 1100.0, 600.0, 21.0),
}


class SpecVehicle(VehicleModel):
    """
    VehicleModel driven by a VehicleSpec and a current payload.

    Payload scales cruise CO2 / energy by
      factor = 1 + MASS_ENERGY_ELASTICITY * payload_kg / kerb_kg
    Idle draw does not depend on payload.
    """

    def __init__(self, spec: VehicleSpec, payload_kg: float = 0.0, name: str | None = None):
        if payload_kg < 0 or payload_kg > spec.capacity_kg:
            raise ValueError(
                f"payload {payload_kg} kg outside [0, {spec.capacity_kg}] for {spec.key}")
        self.spec = spec
        self.payload_kg = float(payload_kg)
        self._name = name or spec.key

    def with_payload(self, payload_kg: float) -> "SpecVehicle":
        """Return a copy of this vehicle carrying payload_kg."""
        clone = object.__new__(type(self))
        SpecVehicle.__init__(clone, self.spec, payload_kg, self._name)
        return clone

    @property
    def mass_factor(self) -> float:
        return 1.0 + config.MASS_ENERGY_ELASTICITY * self.payload_kg / self.spec.kerb_kg

    # --- emissions (tailpipe) ---
    def cruise_cost(self, distance_km: float) -> float:
        return self.spec.cruise_co2_g_km * self.mass_factor * max(0.0, distance_km)

    def idle_cost(self, idle_seconds: float) -> float:
        if self.spec.is_electric:
            return 0.0
        return self.idle_fuel(idle_seconds) / 1000.0 * config.CO2_PER_LITRE[self.spec.fuel]

    # --- fuel / energy ---
    def idle_fuel(self, idle_seconds: float) -> float:
        return self.spec.idle_ml_s * max(0.0, idle_seconds)

    def fuel_ml(self, distance_km: float, idle_seconds: float = 0.0) -> float:
        """Total fuel (mL) for cruising distance_km plus idling idle_seconds."""
        if self.spec.is_electric:
            return 0.0
        cruise_ml = self.cruise_cost(distance_km) / config.CO2_PER_LITRE[self.spec.fuel] * 1000.0
        return cruise_ml + self.idle_fuel(idle_seconds)

    def energy_kwh(self, distance_km: float) -> float:
        """Traction energy (kWh) for electric vehicles; 0 for combustion."""
        return self.spec.kwh_per_km * self.mass_factor * max(0.0, distance_km)

    def energy_cost_inr(self, fuel_ml: float, energy_kwh: float) -> float:
        if self.spec.is_electric:
            return energy_kwh * config.ELECTRICITY_INR_PER_KWH
        return fuel_ml / 1000.0 * config.FUEL_PRICE_INR_PER_L[self.spec.fuel]

    @property
    def name(self) -> str:
        return self._name


class ICEVehicle(SpecVehicle):
    """Petrol car (1.5L): 120 g CO2/km cruise, 0.2 mL/s idle (0.462 g CO2/s)."""

    E_CRUISE_G_PER_KM: float = config.ICE_CRUISE_CO2_PER_KM
    E_IDLE_G_PER_SEC:  float = config.ICE_IDLE_CO2_PER_SEC
    F_IDLE_ML_PER_SEC: float = config.ICE_IDLE_ML_PER_SEC

    def __init__(self, payload_kg: float = 0.0):
        super().__init__(VEHICLE_SPECS["car_petrol"], payload_kg, "ICE")


class EVVehicle(SpecVehicle):
    """Electric car: zero tailpipe CO2; energy and grid CO2 reported separately."""

    E_CRUISE_G_PER_KM: float = config.EV_CRUISE_CO2_PER_KM
    E_IDLE_G_PER_SEC:  float = config.EV_IDLE_CO2_PER_SEC
    F_IDLE_ML_PER_SEC: float = 0.0

    def __init__(self, payload_kg: float = 0.0):
        super().__init__(VEHICLE_SPECS["car_ev"], payload_kg, "EV")


def make_vehicle(vehicle_type: str) -> VehicleModel:
    """
    Return a VehicleModel for 'ICE', 'EV' or any VEHICLE_SPECS key
    (case-insensitive). Raises ValueError for unknown types.
    """
    key = vehicle_type.strip()
    if key.upper() == "ICE":
        return ICEVehicle()
    if key.upper() == "EV":
        return EVVehicle()
    if key.lower() in VEHICLE_SPECS:
        return SpecVehicle(VEHICLE_SPECS[key.lower()])
    raise ValueError(
        f"Unknown vehicle type: {vehicle_type!r}. "
        f"Valid options: ['ICE', 'EV'] + {list(VEHICLE_SPECS)}"
    )
