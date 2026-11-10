"""
config.py — Global Calibration Constants & Configuration
Route-to-Impact (R2I) · Phase 1 Deliverable

All physical constants and model weights live here.
To change any value: update this file, add a citation to docs/assumptions.md,
and get team consensus.

DO NOT scatter magic numbers across other modules.
"""

# ──────────────────────────────────────────────────────────────────────────────
# VEHICLE EMISSION CONSTANTS
# Source: Standard combustion emission factors (Petroleum sector benchmarks)
# ──────────────────────────────────────────────────────────────────────────────

# Grams of CO2 emitted per litre of petrol burned
CO2_PER_LITRE_PETROL: float = 2310.0  # g CO2 / litre

# ICE idle fuel consumption rate for a typical 1.5L petrol engine
ICE_IDLE_ML_PER_SEC: float = 0.2  # mL / second  (~12 mL/min)

# Derived: ICE idle CO2 emission rate = ICE_IDLE_ML_PER_SEC * CO2_PER_LITRE_PETROL / 1000
ICE_IDLE_CO2_PER_SEC: float = ICE_IDLE_ML_PER_SEC * CO2_PER_LITRE_PETROL / 1000  # 0.462 g/s

# ICE cruise CO2 emission rate for a 1.5L petrol engine at optimal speed
ICE_CRUISE_CO2_PER_KM: float = 120.0  # g CO2 / km

# EV point-of-use emissions (zero tailpipe — physics)
EV_IDLE_CO2_PER_SEC: float = 0.0   # g CO2 / second
EV_CRUISE_CO2_PER_KM: float = 0.0  # g CO2 / km (no tailpipe)

# ──────────────────────────────────────────────────────────────────────────────
# CONGESTION PROXY CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Base idle duration per intersection — midpoint of 15–20s calibrated benchmark
# Citation: OPEN (OQ-2) — must be cited before Phase 4 exit
T_BASE_IDLE: float = 17.5  # seconds

# Congestion score component weights — must sum context is [0, 1] normalised
DEGREE_WEIGHT: float = 0.5   # w_d — intersection complexity (node degree)
SIGNAL_WEIGHT: float = 0.3   # w_s — traffic signal presence
ROAD_CLASS_WEIGHT: float = 0.2  # w_c — highway classification tier

# Road classification → congestion weight mapping
HIGHWAY_CLASS_WEIGHTS: dict = {
    "motorway": 0.1,      # High-speed, low signal density
    "trunk": 0.3,
    "primary": 1.0,       # Highest urban congestion weight
    "secondary": 0.7,
    "tertiary": 0.5,
    "residential": 0.2,
    "unclassified": 0.3,
    "service": 0.1,
}
HIGHWAY_CLASS_DEFAULT: float = 0.3  # fallback for unknown highway types

# ──────────────────────────────────────────────────────────────────────────────
# ROUTING CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Time-preference weighting in edge cost: alpha * T_travel
# Higher alpha = prefer faster routes; 0.0 = pure emission minimisation
# OQ-4: Optimal value resolved in Phase 10 sensitivity sweep
ALPHA: float = 1.0  # Optimal value identified in Phase 10 sensitivity sweep

# ──────────────────────────────────────────────────────────────────────────────
# OSM / GRAPH CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Default demo city (OQ-1 Resolved: Bengaluru)
DEFAULT_CITY: str = "Bengaluru"
DEFAULT_DISTRICT: str = "Koramangala"

# Default demo OD pair (Koramangala 4th Block -> Indiranagar 100 Feet Rd)
DEFAULT_ORIGIN_LAT: float = 12.9352
DEFAULT_ORIGIN_LON: float = 77.6245
DEFAULT_DEST_LAT: float = 12.9716
DEFAULT_DEST_LON: float = 77.5946

# OSM network type — drive only (no pedestrian paths)
OSM_NETWORK_TYPE: str = "drive"

# Path to serialised graph
GRAPH_CACHE_PATH: str = "data/raw/koramangala.graphml"

# ──────────────────────────────────────────────────────────────────────────────
# BENCHMARK CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Number of OD pairs in Monte Carlo benchmark
BENCHMARK_N_TRIPS: int = 200
BENCHMARK_SEED: int = 42  # Fixed seed for reproducibility

# Performance target from NFR: pathfinding must complete in < 2.0 seconds
PERF_TARGET_SECONDS: float = 2.0

# ──────────────────────────────────────────────────────────────────────────────
# v2: FUEL, ENERGY & COST CONSTANTS  (see docs/assumptions.md, section "v2")
# ──────────────────────────────────────────────────────────────────────────────

# Tailpipe CO2 per litre by fuel (combustion stoichiometry; IPCC 2006 defaults)
CO2_PER_LITRE: dict = {"petrol": 2310.0, "diesel": 2680.0}

# Retail prices, Bengaluru, late 2025 (assumption — update as prices change)
FUEL_PRICE_INR_PER_L: dict = {"petrol": 103.0, "diesel": 89.0}
ELECTRICITY_INR_PER_KWH: float = 8.0   # commercial EV charging tariff (assumption)

# Indian grid emission factor (CEA CO2 Baseline Database, ~0.71 kg/kWh)
GRID_CO2_G_PER_KWH: float = 710.0

# Mass–energy elasticity: fractional increase in cruise energy per fractional
# increase in vehicle mass. Literature range 0.5–0.7 for urban drive cycles
# (US NRC 2010, ICCT lightweighting studies). Midpoint used.
MASS_ENERGY_ELASTICITY: float = 0.6

# Fleet stop modelling
STOP_SERVICE_S: float = 120.0          # time spent at each delivery stop
STOP_ENGINE_ON_FRACTION: float = 0.25  # share of service time the engine idles
