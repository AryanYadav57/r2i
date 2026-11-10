# R2I v2 — Combined Implementation Plan (Core + UI)

> **Context:** R2I is moving from an SIH submission to a personal portfolio project.
> v2 adds **fleet delivery routing** and replaces the Streamlit front end with a
> **dynamic, 3D web app** that explains the problem through its own demo.
> This plan supersedes `docs/implementation_plan.md` (the SIH Phase 0–15 plan),
> which stays as history.

---

## 1. Goals

| # | Goal | Done when |
|---|---|---|
| G1 | Correct, honest engine | CO₂, fuel and ₹ are reported separately from the routing cost; every constant is cited in `docs/assumptions.md` |
| G2 | Fleet delivery planning | Capacitated VRP with time windows over R2I costs, mixed ICE/EV fleet, compared against a distance-only plan from the same solver |
| G3 | Explains itself visually | A first-time visitor understands "shortest ≠ cleanest" from the Story tab in under 2 minutes |
| G4 | Portfolio-ready | Live deployed demo, README hero video, CI badges, Method write-up |

## 2. Target app structure

| Tab | Purpose |
|---|---|
| **Story** | Scroll-driven 3D explainer (hook → idle cost → congestion → algorithm → race → EV → scale to fleet) |
| **Map** | Existing map layer kept: point-to-point explorer (search, baseline vs R2I, ICE/EV, layer toggles) |
| **Fleet** | Dispatcher console: Setup → Plan → Simulate → Report |
| **Method** | Formulas, assumptions, benchmarks, limitations |

## 3. Target repository layout

```
r2i/
├── src/r2i/                 # engine (existing package, extended)
│   ├── graph/  models/  routing/  evaluation/
│   ├── fleet/               # NEW: matrix, solver, payload, simulation, insights
│   └── config.py
├── api/                     # NEW: FastAPI service wrapping src/r2i
│   ├── main.py  schemas.py  routes/
├── web/                     # NEW: React + Vite + TypeScript front end
│   ├── src/tabs/{story,map,fleet,method}/
│   ├── src/map/             # shared MapLibre + deck.gl layers
│   └── public/scenarios/    # precomputed demo JSON
├── lab/                     # existing Streamlit app, kept as internal tool
├── scripts/                 # graph download, scenario precompute, benchmarks
├── tests/                   # engine + API tests
└── docs/
```

## 4. Tech stack

| Layer | Choice |
|---|---|
| Engine | Python 3.11, NetworkX, OSMnx (existing) |
| Fleet solver | Google OR-Tools (CVRPTW, heterogeneous fleet) |
| API | FastAPI + Pydantic, uvicorn |
| Front end | React + Vite + TypeScript, Zustand (state), TanStack Query (API) |
| Map / 3D | MapLibre GL (no API key), deck.gl (TripsLayer, ColumnLayer, PathLayer), react-three-fiber for close-up scenes |
| Motion | GSAP ScrollTrigger (Story), deck.gl transitions |
| Charts | Visx or Recharts |
| Quality | pytest, ruff, mypy (engine); Vitest + Playwright (web); GitHub Actions |
| Hosting | Vercel (web), Render / Fly.io / HF Spaces (API) |

---

## 5. Phases at a glance

| Phase | Track | Name | Depends on |
|---|---|---|---|
| 0 | Core | Repo reset & foundations | — |
| 1 | Core | Engine correctness & vehicle physics v2 | 0 |
| 2 | Core | API layer | 1 |
| 3 | UI | Web shell + Map tab | 2 (API contract only) |
| 4 | UI + Core | Race scene & sandbox interactions | 3 |
| 5 | Core | Fleet engine | 1 (can run in parallel with 3–4) |
| 6 | UI | Fleet tab (dispatcher console) | 4, 5 |
| 7 | UI | Story mode | 4, 6 |
| 8 | Both | Method tab, polish & deploy | 6, 7 |
| 9 | Both | Stretch goals | 8 |

Two tracks can run side by side: **Phase 5 (fleet engine)** has no UI dependency and
can be built while **Phases 3–4** are in progress.

---

## Phase 0 — Repo reset & foundations
**Goal:** a clean, honest base to build on.

**Core**
- [ ] Fix the CO₂ reporting bug: `compute_eco_metrics` (`routing/router.py`) adds `total_weight`, which includes `α·travel_time`, into `total_co2_g`. Report `cruise_co2_g + idle_co2_g` as CO₂, and keep `total_weight` as a separate `routing_cost` field.
- [ ] Add a regression test: with α = 1 and a non-zero travel time, `total_co2_g` must equal cruise + idle CO₂ only.
- [ ] Remove the unused `scikit-learn` from `requirements.txt`.
- [ ] Make the router CLI actually load the graph and print a comparison.
- [ ] Move dev dependencies into `pyproject.toml` (`[project.optional-dependencies] dev/api/lab`).
- [ ] Add ruff and mypy configs, and a GitHub Actions workflow running lint + tests.

**Repo / docs**
- [ ] Rebrand: README, `pyproject.toml` description (drop "SIH 2026").
- [ ] Move SIH-only docs (pitch deck, judge Q&A, team tasks, one-pager) to `docs/archive/sih/`.
- [ ] Move `app/` to `lab/` (Streamlit stays usable as the internal lab tool).
- [ ] Add a LICENSE (MIT suggested).

**Exit:** CI green; corrected CO₂ test passes; README describes the v2 direction.

---

## Phase 1 — Engine correctness & vehicle physics v2
**Goal:** a physics model good enough for fleet decisions.

- [ ] **Separate cost from emissions everywhere:** each metric dict carries `co2_g`, `fuel_ml`, `fuel_cost_inr`, `idle_s`, `routing_cost`.
- [ ] **Fuel price config:** `FUEL_PRICE_INR_PER_L`, `ELECTRICITY_INR_PER_KWH` in `config.py`.
- [ ] **Vehicle classes** as `VehicleModel` subclasses or a data-driven `VehicleSpec`: 2-wheeler, EV 3-wheeler, small commercial van (petrol/CNG/diesel), EV van. Fields: cruise g/km, idle mL/s, kerb mass, payload capacity, battery kWh, range.
- [ ] **Payload-aware emissions:** cruise cost scales with total mass (`base × (1 + k · payload/kerb_mass)`), with `k` cited.
- [ ] **EV energy model:** kWh/km (payload-aware) so EV routes report energy and ₹, not just "0 g".
- [ ] **Stop dwell cost:** per-delivery dwell time, plus idle if the engine stays on (configurable).
- [ ] Update `docs/assumptions.md` with a source for every new constant (ARAI / ICCT / manufacturer data).
- [ ] Tests: monotonicity in payload, EV ≥ 0 energy, class-specific invariants.

**Exit:** all vehicle classes pass the tests; one OD pair shows sensible ₹ / CO₂ / kWh for every class.

---

## Phase 2 — API layer
**Goal:** the engine is usable from the web.

- [ ] `api/main.py`: FastAPI app; graph loaded and featurised **once** at startup.
- [ ] Endpoints:
  - `GET  /graph` — nodes and edges as GeoJSON with `congestion_score`, `is_signal`, `highway` (simplified, cached)
  - `POST /route/compare` — origin, destination, vehicle, α → both paths as coordinates plus metrics and avoided nodes
  - `POST /route/sweep` — α sweep → time vs CO₂ points (for the trade-off chart)
  - `POST /route/explore` — Dijkstra visit order (for the "wave" animation)
  - `GET  /geocode?q=` — proxies Nominatim with caching and a proper User-Agent
- [ ] Pydantic schemas shared as the API contract; OpenAPI docs exposed.
- [ ] Response times: `/route/compare` < 300 ms on the Koramangala graph.
- [ ] API tests with FastAPI's `TestClient`.

**Exit:** the front end can be built entirely against the OpenAPI contract.

---

## Phase 3 — Web shell + Map tab
**Goal:** the new app exists, and the existing map experience lives in its own tab.

**Shell**
- [ ] Vite + React + TS scaffold in `web/`; tab router (Story / Map / Fleet / Method).
- [ ] Design tokens: dark map theme, green = R2I, red/amber = baseline, Instrument Serif / Inter / JetBrains Mono (carried over from the Streamlit look).
- [ ] Shared `<CityMap>` component: MapLibre base plus a deck.gl overlay, 2D/3D toggle with extruded buildings.

**Map tab (port of the existing map layer)**
- [ ] Place search (via `/geocode`) and click-to-place origin/destination.
- [ ] Baseline vs R2I routes, ICE/EV toggle, α slider.
- [ ] Layer toggles: congestion heat, signals, road class.
- [ ] Comparison card (distance, time, idle s, CO₂, ₹) and a "why this route?" list of avoided junctions (click → fly to it).
- [ ] The Google Maps Live Navigation page stays available in `lab/`; migrating it to MapLibre is optional.

**Exit:** the Map tab matches or exceeds the current Streamlit map features.

---

## Phase 4 — Race scene & sandbox interactions
**Goal:** the single most convincing visual, plus the plumbing everything else reuses.

- [ ] **Race:** two vehicles animate along baseline and R2I routes (deck.gl `TripsLayer`) with live counters side by side; idle stops show exhaust puffs.
- [ ] **3D congestion columns:** intersections as `ColumnLayer` (height = score, colour = heat); factor toggles animate the heights.
- [ ] **Dijkstra wave:** animate the `/route/explore` visit order across the network.
- [ ] **α trade-off chart:** time vs CO₂ curve from `/route/sweep`; dragging the slider moves a point along the curve.
- [ ] **Congestion brush:** paint extra congestion onto roads → re-route (the API accepts per-node overrides).
- [ ] Shared `useTimeline()` hook (play / pause / speed / scrub), reused by Fleet and Story.

**Exit:** the race runs at 60 fps on a mid-range laptop; all interactions respond in < 500 ms.

---

## Phase 5 — Fleet engine (core)
**Goal:** plan a day of deliveries for a mixed fleet, fairly compared against distance-only planning.

- [ ] `fleet/matrix.py` — **all-pairs cost table** between hub and stops via repeated single-source Dijkstra; separate tables for distance, time and R2I cost per vehicle class; cached to disk per scenario.
- [ ] `fleet/model.py` — data classes: `Hub`, `Order` (location, weight, time window, service time), `FleetVehicle` (class, capacity, shift, range), `Scenario`.
- [ ] `fleet/solver.py` — OR-Tools CVRPTW:
  - capacity and time-window dimensions
  - **heterogeneous fleet:** a cost table per vehicle class (this is what lets EVs win congested clusters)
  - EV range as a distance/energy dimension
  - solver time limit and fixed seed for reproducibility
- [ ] **Fair baseline:** the same solver, constraints and time limit, but a distance-only cost table.
- [ ] `fleet/payload.py` — OR-Tools arc costs are fixed, so payload is handled in two steps: (1) solve with average-payload costs, (2) re-order stops within each route by local search (2-opt / or-opt) scored by **true payload-aware fuel**. Document this approximation in the Method tab.
- [ ] `fleet/simulate.py` — convert plans into **timestamped trajectories** (coordinates + time per vertex for `TripsLayer`) plus events: depart, drive, idle at junction, stop, deliver, late.
- [ ] `fleet/insights.py` — rule-based plain-language explanations with map anchors (e.g. "EV-2 assigned to the Silk Board cluster: 14 signals, ~9 min petrol idling avoided").
- [ ] `fleet/scenarios.py` — synthetic order generator (seeded) and one curated **preset**: "Koramangala dark store · 30 orders · 4 vans + 3 EV 3-wheelers".
- [ ] API: `POST /fleet/plan` (returns both plans, trajectories, events, metrics, insights) and `GET /fleet/scenarios/{id}`.
- [ ] `scripts/precompute_scenarios.py` → `web/public/scenarios/*.json`.
- [ ] **Benchmark:** 100 random seeded scenarios → distribution of ₹ / CO₂ / km / on-time deltas, saved as CSV for the Method tab.
- [ ] Tests: capacity never exceeded, time windows respected (or flagged), every order served exactly once, baseline and R2I use identical constraints.

**Exit:** the preset plans in < 10 s; the benchmark reports honest gains, including scenarios where R2I does not win.

---

## Phase 6 — Fleet tab (dispatcher console)
**Goal:** fleet planning that people understand by watching it.

Layout: steps bar (Setup / Plan / Simulate / Report) · left panel (orders + fleet roster) · centre 3D map · right panel (scoreboard + insights) · bottom timeline with a Gantt chart.

**6a — Preset first (read-only Setup)**
- [ ] Load the preset JSON; show hub, numbered stops and the fleet roster.
- [ ] **Plan view:** a colour per vehicle, baseline as dashed ghost lines; Overlay / Split (synced cameras) / Single toggle.
- [ ] **Simulate:** timeline scrubber 09:00–18:00, 1× / 10× / 60×; vehicles move along trajectories; payload bars shrink on each drop; exhaust puffs at idle-heavy junctions for ICE; ghost baseline fleet runs at the same time.
- [ ] **Gantt:** one row per vehicle (drive / idle / stop blocks, time-window markers, late deliveries in red); hover syncs with the map.
- [ ] **Scoreboard:** baseline vs R2I for km, litres, kWh, ₹, kg CO₂, idle min, on-time %, vehicles used; scale-up control (day → month → year, fleet × N).
- [ ] **Insights panel:** clickable, camera flies to the anchor.
- [ ] **Vehicle drill-down:** stop list, payload-over-time chart, fuel per leg, emissions split (driving / idling / payload).

**6b — Editable Setup**
- [ ] Add orders by map click, CSV upload or "randomise"; edit weight and time window.
- [ ] Add/remove vehicles; change classes.
- [ ] Re-plan via `/fleet/plan` with a progress state.

**6c — What-if controls**
- [ ] EV share slider (0–100%) with a fleet CO₂ vs EV share chart.
- [ ] Paint a traffic jam → re-plan.
- [ ] Tighten time windows; α slider.
- [ ] Export the report as PNG/PDF.

**Exit:** a new visitor can run the preset end to end without instructions; Simulate stays smooth with 7 vehicles at 60×.

---

## Phase 7 — Story mode
**Goal:** explain the problem in under 2 minutes, mostly with visuals.

- [ ] Scroll-driven sections (GSAP ScrollTrigger) controlling one shared map camera:
  1. **Hook** — dark 3D city, flowing traffic, a "litres burned idling" counter
  2. **The hidden cost** — fly to one busy junction; react-three-fiber close-up with stopped cars and exhaust particles; 0.462 g/s meter
  3. **Congestion made visible** — columns rise; factor toggles
  4. **The algorithm** — Dijkstra wave
  5. **The race** — reuses the Phase 4 race
  6. **EV vs petrol** — route changes on toggle
  7. **Scale to a fleet** — vans dispatch from the hub → "Open Fleet tab" call to action
- [ ] All Story data precomputed (no API calls on scroll).
- [ ] `prefers-reduced-motion`: replace animations with static frames and captions.
- [ ] Mobile: simplified 2D fallback.

**Exit:** Lighthouse performance ≥ 80 on desktop; the story works with reduced motion.

---

## Phase 8 — Method tab, polish & deploy
**Goal:** portfolio-ready.

- [ ] **Method tab:** formulas with live mini-visuals, the assumptions table with sources, benchmark charts (Phase 5 CSV), limitations (static congestion proxy, modelled not measured, the payload approximation).
- [ ] Deploy: web on Vercel, API on Render / Fly / HF Spaces; graph and scenarios baked into the image; CORS locked to the web origin.
- [ ] Monitoring: basic request logging and uptime check; cold-start note in the UI.
- [ ] README: hero video/GIF, live link, architecture diagram, how to run locally, CI and coverage badges.
- [ ] Write-up / blog post: "Why the shortest route isn't the cleanest one".
- [ ] Accessibility pass: keyboard navigation for tabs and controls, colour-blind-safe route colours (pattern + colour), text alternatives for charts.
- [ ] Playwright smoke tests: each tab loads; the preset fleet plan plays.

**Exit:** a public URL that a stranger can use; README sells the project in 30 seconds.

---

## Phase 9 — Stretch goals
- [ ] **Time-of-day congestion:** morning / afternoon / night profiles; the timeline drives them.
- [ ] **Data-driven congestion (ML v2):** learn idle time from open traffic or GPS data; compare against the structural proxy in the Method tab.
- [ ] **EV charging stops** in the solver.
- [ ] **More cities:** city picker; graph download pipeline in CI.
- [ ] **Live re-routing:** inject a mid-day jam and re-plan the remaining stops.

---

## 6. Milestones

| Milestone | Phases | What you can show |
|---|---|---|
| M1 — Honest engine | 0–2 | Corrected numbers, API with docs, CI badges |
| M2 — Race demo | 3–4 | Map tab + the race scene (first portfolio-worthy GIF) |
| M3 — Fleet demo | 5–6a | Preset fleet plan, simulation and scoreboard |
| M4 — Full app | 6b–7 | Editable fleet, what-ifs, Story mode |
| M5 — Launch | 8 | Deployed app, README video, write-up |

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| R2I shows small or no gains on some scenarios | Report the full distribution honestly; explain when and why it wins (dense signals, EV mix) |
| OR-Tools can't model payload-dependent arc costs directly | Two-step solve + payload-aware local search (Phase 5); documented as an approximation |
| 3D performance on weaker machines | Precomputed data, simplified geometry, 2D fallback, reduced-motion mode |
| Free API hosting cold starts | Precomputed preset loads without the API; show a "warming up" state |
| Nominatim usage limits | Proxy through the API with caching; debounce search |
| Scope creep in the UI | Ship the preset-first Fleet tab (6a) before editable Setup (6b) |
