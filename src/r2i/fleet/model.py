"""fleet/model.py - Scenario data classes. Times are seconds since midnight."""

from __future__ import annotations

from dataclasses import dataclass, field

from r2i import config
from r2i.models.vehicle import VEHICLE_SPECS, VehicleSpec


@dataclass(frozen=True)
class Hub:
    lat: float
    lon: float
    node: int


@dataclass(frozen=True)
class Order:
    id: str
    lat: float
    lon: float
    node: int
    weight_kg: float
    tw_start_s: int
    tw_end_s: int
    service_s: float = config.STOP_SERVICE_S


@dataclass(frozen=True)
class FleetVehicle:
    id: str
    spec: VehicleSpec
    shift_start_s: int = 9 * 3600
    shift_end_s: int = 18 * 3600

    @classmethod
    def of(cls, vid: str, spec_key: str, **kw) -> "FleetVehicle":
        return cls(vid, VEHICLE_SPECS[spec_key], **kw)

    @property
    def range_km(self) -> float:
        if self.spec.is_electric and self.spec.kwh_per_km > 0:
            return self.spec.battery_kwh / self.spec.kwh_per_km
        return 10_000.0


@dataclass
class Scenario:
    hub: Hub
    orders: list
    vehicles: list
    name: str = "custom"
    meta: dict = field(default_factory=dict)
