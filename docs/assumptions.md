# Assumptions & Literature Citations
## Route-to-Impact (R2I) · docs/assumptions.md

This document must cite every calibration constant in config.py.
It is required for Phase 4 exit condition.

---

## T_BASE_IDLE = 17.5 seconds

**Status:** OPEN (OQ-2) — Citation required before Phase 4 exits.

**Placeholder rationale:**
The 15–20 second idle benchmark per intersection is derived from published
urban transit studies measuring stop-and-go engine behaviour at signalised
intersections in Indian cities. A peer-reviewed citation must be inserted here.

**Required citation format:**
> [Author(s)], "[Paper Title]", [Journal/Conference], [Year].
> Relevant finding: average idle duration at signalised intersections = X–Y seconds.

---

## ICE_IDLE_ML_PER_SEC = 0.2 mL/s

**Rationale:** A typical 1.5L petrol engine consumes approximately 0.2 mL/s
(12 mL/min) while idling at neutral. This is consistent with published
manufacturer engine bench-test data for small-displacement Indian market vehicles
(e.g., Maruti Suzuki 1.2L–1.5L, Hyundai i20 1.2L).

**Citation:** Standard vehicle manufacturer idle consumption benchmarks.
Specific citation to be inserted during Phase 4.

---

## CO2_PER_LITRE_PETROL = 2,310 g CO2/litre

**Rationale:** Well-established combustion stoichiometry.
1 litre of petrol = ~0.74 kg hydrocarbons; complete combustion yields ~2.31 kg CO2.

**Citation:** IPCC Guidelines for National Greenhouse Gas Inventories, Volume 2,
Chapter 3 (Mobile Combustion), Table 3.2.1.

---

## ICE_CRUISE_CO2_PER_KM = 120 g CO2/km

**Rationale:** European Environment Agency average for small petrol cars
(sub-1600cc, WLTP test cycle). Representative for Indian market vehicles.

**Citation:** EEA, "CO2 emission performance standards for cars and vans", 2023.

---

*Update this file with formal citations before Phase 4 exit review.*

---

## v2 assumptions (fleet & cost model)

| Constant | Value | Basis |
|---|---|---|
| CO₂ per litre | petrol 2310 g, diesel 2680 g | Combustion stoichiometry (IPCC 2006 defaults) |
| Fuel price | petrol ₹103/L, diesel ₹89/L | Bengaluru retail, late 2025 — update as needed |
| Electricity tariff | ₹8/kWh | Typical commercial EV charging tariff (assumption) |
| Grid emission factor | 710 g CO₂/kWh | CEA CO₂ Baseline Database (India, ~0.71 kg/kWh) |
| Mass–energy elasticity | 0.6 | Midpoint of 0.5–0.7 reported for urban cycles (US NRC 2010; ICCT lightweighting studies) |
| Petrol 2-wheeler | 51 g/km, 0.05 mL/s idle, 110 kg, 20 kg payload | ~45 km/L commuter motorcycle |
| EV 3-wheeler cargo | 0.075 kWh/km, 400 kg, 300 kg payload, 8 kWh | ~100 km range e-cargo 3W |
| Diesel mini-truck | 179 g/km, 0.25 mL/s idle, 1000 kg, 750 kg payload | ~15 km/L Tata Ace-class LCV |
| EV mini-truck | 0.14 kWh/km, 1100 kg, 600 kg payload, 21 kWh | Ace EV-class, ~150 km range |
| Stop service time | 120 s, engine on 25% of it | Last-mile delivery assumption |

EV "CO₂" in route metrics is **tailpipe** (zero); upstream grid CO₂ is reported
separately as `grid_co2_g` so EVs are not presented as emission-free.
