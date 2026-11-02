"""Offline-first traffic and incident scenario inputs for reproducible R2I runs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TrafficSnapshot:
    name: str
    source: str
    observed_at: str
    confidence: float
    delay_by_highway: dict[str, float]
    closed_highways: tuple[str, ...] = ()
    unavailable: bool = False


def get_traffic_snapshot(name: str, google_route: dict[str, Any] | None = None) -> TrafficSnapshot:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if google_route and google_route.get("traffic_segments"):
        # Local edge-to-interval matching is performed by the routing evaluator.
        return TrafficSnapshot("Live Google traffic", "Google Routes API", now, 0.7, {})
    scenarios = {
        "Normal conditions": TrafficSnapshot(name, "Bundled road-class estimate", now, 0.45, {}),
        "Peak bottleneck": TrafficSnapshot(name, "Deterministic demo scenario", now, 0.35,
            {"primary": 2.0, "secondary": 1.55, "tertiary": 1.25}),
        "Incident / road closure": TrafficSnapshot(name, "Deterministic demo scenario", now, 0.35,
            {"primary": 1.45, "secondary": 1.2}, ("primary_link",)),
        "Stale / missing traffic": TrafficSnapshot(name, "Fallback: road-class estimate", now, 0.15, {}, unavailable=True),
    }
    return scenarios.get(name, scenarios["Normal conditions"])
