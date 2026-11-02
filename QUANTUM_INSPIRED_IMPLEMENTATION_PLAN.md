# R2I Quantum-Inspired Network Route Optimizer — Implementation Plan

**Purpose:** Convert the project brief shown in the attached hackathon screenshot into an implementable, judge-ready plan for comparing classical routing with a quantum-inspired route selector under congestion, latency, and failure constraints.

**Project fit:** Route-to-Impact (R2I), Bengaluru road network, existing Streamlit + NetworkX prototype. The screenshot is treated as a short challenge brief, not as a full official rulebook. Confirm track-specific submission rules with the organizers before final submission.

## 1. Recommended solution

Build a **hybrid classical + quantum-inspired optimizer**. Keep the road network, route feasibility, and candidate generation classical. Generate a bounded set of valid candidate routes with Yen’s K-shortest paths / constrained Dijkstra, score each route against time, emissions, congestion, reliability, and service cost, then use a small **QUBO solved by simulated annealing** to select the best candidate under a chosen operating scenario.

This is appropriate for a hackathon prototype because it is explainable, runs on ordinary hardware, produces valid routes by construction, and provides a fair baseline comparison. Describe it precisely as *quantum-inspired optimization using classical simulated annealing*; do not claim quantum-hardware execution or a performance advantage unless measured.

## 2. Challenge interpretation and judging story

The screenshot calls for:

- A quantum-inspired network route optimizer (ET-08 in the visible row).
- Classical shortest-path versus quantum-inspired route selection.
- Congestion, latency, and failure constraints.
- Qualcomm Cloud AI Playground.
- Network topology, route comparison, and latency/cost score.

Translate that into a clear product claim: **Given the same road graph and traffic snapshot, R2I compares a fastest classical route with a quantum-inspired multi-objective route, while respecting route validity and user constraints.** This aligns with the existing project’s environmental purpose and allows the demo to quantify when trade-offs are useful.

The optimizer itself should be deterministic enough to explain and benchmark. Qualcomm Cloud AI Playground is an optional supporting component for generating a concise natural-language explanation of a result; it should not be represented as the route optimizer. Keep routing operational when that service is unavailable. Verify the exact playground/API model, access, latency and permitted use for the event account before integrating it.

## 3. Target behavior and acceptance criteria

For each origin/destination and scenario, the app should show:

1. **Classical baseline:** fastest feasible route on the selected graph and traffic snapshot.
2. **R2I route:** lowest composite-cost feasible candidate selected by the simulated-annealing QUBO (or classical fallback if the optimizer times out/fails).
3. **Constraints:** closed/unavailable edges excluded; maximum detour, time budget, reliability threshold, and optional vehicle restrictions enforced.
4. **Route metrics:** distance, estimated time, estimated CO₂/fuel, congestion exposure, reliability/risk, algorithm runtime, and routing-data source/timestamp.
5. **Cost score:** a documented score, such as normalized weighted objective and/or estimated compute/service cost per run. Never conflate the abstract optimization score with monetary cost.
6. **Reproducibility:** fixed input scenario + random seed recreates the same benchmark record.
7. **Honest result:** if both methods choose the same route or input data has no differentiated traffic, say so. Do not fabricate savings.

Suggested MVP targets (measure and revise against actual local graph size): return a valid result under 2 seconds for the bundled neighborhood graph; zero constraint violations; at least 95% successful route completion over the benchmark set; report median/p95 runtime, and fail over to classical routing within a bounded timeout.

## 4. Architecture

```text
Landmarks / GraphML / Traffic snapshot / Failure scenario
                         │
                  Input validation
                         │
       ┌─────────────────┴────────────────┐
       │                                  │
Classical fastest path            Candidate generator
Dijkstra / A*                     K shortest feasible paths
       │                                  │
       │                       Route feature + cost builder
       │                                  │
       │                      QUBO one-hot candidate selector
       │                      Simulated annealing (CPU)
       └─────────────────┬────────────────┘
                         │
        Feasibility check + fallback + metrics
                         │
             Streamlit comparison + map + report
```

Suggested module boundaries (keep existing app functional during migration):

- `r2i_engine.py`: graph parsing, normalized edge feature extraction, path metrics, classical baseline, candidate validation.
- `candidate_routes.py`: bounded K-shortest route generation and candidate diversity/dominance pruning.
- `quantum_inspired.py`: QUBO construction, simulated annealing adapter, deterministic seed, time budget, solver metadata. This stays separate from core road-data parsing.
- `traffic_provider.py`: traffic snapshot interface and offline scenario fixtures; external provider isolated behind a timeout and graceful fallback.
- `benchmark.py`: fixed OD/scenario suite, paired metrics, raw CSV/JSON output, summary tables.
- `app.py`: inputs, scenario selection, comparison/map, transparent limitations and data freshness.

## 5. Data and graph model

### 5.1 Road graph

Use the existing OSMnx/NetworkX directed multigraph and bundled GraphML. Normalize each traversable edge into stable fields:

- Unique directed edge ID, source and target node IDs, length, road class, speed limit if present.
- Estimated free-flow time and calibrated baseline emissions/energy.
- Congestion observation or explicit estimated value, observation time and confidence.
- Availability/failure state and reliability probability/confidence.
- Vehicle compatibility and any modeled restrictions.

Never mutate the source graph while benchmarking scenarios; derive an immutable scenario view/edge-weight map. Keep repeated parallel road edges explicit and choose a valid edge consistently for path metrics.

### 5.2 Traffic and bottleneck data

Create a provider-neutral `TrafficSnapshot` schema with `edge_id`, speed category/speed ratio or delay factor, observed time, source and confidence. For Google Routes traffic intervals, map points to nearby OSM edges using a documented spatial match radius and retain the source/time. A route-level travel-time ratio is a coarse fallback only; label it route-wide, do not imply it measures every intersection. If matched local intervals are absent, use clearly labeled road-class/synthetic scenario data.

For repeatable evaluation, include offline scenarios: free flow, peak bottleneck on named corridor(s), incident/edge closure, and stale/missing traffic. Live APIs are optional for the demo, never required for the benchmark or app startup.

### 5.3 Failure/uncertainty

Represent an unavailable edge as a hard exclusion. Represent uncertain availability/reliability separately from congestion. For a simple reliability objective, route failure probability under independence is `1 - product(1 - p_e)`; document independence as an approximation. Avoid using an arbitrary traffic penalty as a proxy for failure risk.

## 6. Objective formulation

### 6.1 Route-level features

For each feasible candidate route `r`, compute:

- `T_r`: estimated travel time under the same snapshot.
- `E_r`: estimated CO₂ (or energy/fuel for selected powertrain).
- `C_r`: congestion exposure, e.g. distance/time weighted by traffic severity.
- `R_r`: route failure risk or reliability penalty.
- `D_r`: distance / detour ratio.
- `L_r`: observed or modeled inference/routing latency, kept separate from road travel time.

Normalize each metric against the candidate set or documented fixed bounds, clipping outliers. Save the raw values alongside normalized values so the explanation remains meaningful.

### 6.2 Weighted objective and constraints

For route `r` use:

`J_r = wT*T_norm + wE*E_norm + wC*C_norm + wR*R_norm + wD*D_norm`

Weights are non-negative and normalized to sum to one. The eco/time control maps to an explicit documented weight policy; reliability and detour limits should generally be hard constraints rather than weights. If constraints are softened for experimentation, report each violation and penalty.

Classical baseline: minimize travel time subject to the same hard constraints. The R2I/QI route: choose minimum `J_r` among the same feasible candidates. For a fair benchmark, also run a **classical weighted-cost shortest-path baseline** with the same objective. This isolates whether the annealing selector adds value beyond merely changing the objective.

### 6.3 QUBO

Use one binary variable per candidate route, `x_i ∈ {0,1}`. The initial QUBO is intentionally small:

`E(x) = Σ_i J_i x_i + λ(Σ_i x_i − 1)^2`

The penalty `λ` must exceed the largest possible objective swing so invalid zero-route/multi-route assignments are never optimal. Decode the lowest-energy sample, verify exactly one route is selected, and independently validate the selected path and hard constraints. If the sample is invalid or no feasible candidates exist, use the classical fallback and clearly mark it.

This one-hot formulation makes connectivity valid by construction because each variable represents a complete feasible route. Do not begin with one binary variable per road edge: flow/conservation constraints make the first prototype harder to debug and easier to decode into disconnected paths.

## 7. Implementation phases and deliverables

### Phase 0 — Freeze scope and demo story

- Confirm the hackathon’s exact rubric, data/API rules, and whether Qualcomm Cloud AI Playground usage is expected or just listed as a tool.
- Pick a compact Bengaluru study area covered by the bundled graph and 3–5 OD pairs with known alternate corridors.
- Choose the demo claim and do not promise global optimality or quantum speedup.
- Define scenario table, evaluation metrics, demo fallback, and team responsibilities.

**Done when:** one-page scope, architecture sketch, acceptance criteria and a fixed demo script exist.

### Phase 1 — Establish trustworthy classical baseline

- Audit graph directionality, missing edge attributes, multiedge handling, coordinate snapping and disconnected pairs.
- Implement/retain classical fastest Dijkstra using travel-time weights; use A* only if the heuristic is admissible for the chosen cost.
- Create one shared path-metric function used for both algorithms; return raw distance/time/fuel/CO₂/congestion/risk and compute time.
- Add fixed OD pairs and deterministic input fixtures; save baseline outputs.
- Confirm units and label emissions as estimates unless calibrated measurements exist.

**Done when:** every benchmark pair has a valid route and baseline metrics recompute consistently from the route edges.

### Phase 2 — Scenario and reliability model

- Introduce immutable traffic snapshots and timestamp/confidence fields.
- Add offline peak congestion, incident closure, low-confidence/stale traffic, and no-data cases.
- Add edge closures and route constraints (max detour and maximum failure risk) with explicit validation.
- Match live traffic intervals to local graph edges when available; provide an explicit fallback indicator.

**Done when:** the same scenario can be replayed offline; closed edges never appear in output paths; stale/missing traffic triggers a visible fallback.

### Phase 3 — Candidate route generation

- Generate `K` feasible alternatives with Yen’s algorithm using fastest-time edge cost; begin with K=10, increase only if useful.
- Add controlled diversity (avoid near-duplicate alternatives) without changing validity.
- Recompute all route metrics through the shared evaluator.
- Remove dominated candidates (another route is no worse in every objective and better in at least one).
- Enforce a bounded candidate count and generation timeout; retain the fastest feasible route at all times.

**Done when:** candidate list has valid complete paths, contains the classical baseline, is diverse enough for the demo and remains bounded in runtime/memory.

### Phase 4 — Quantum-inspired selector

- Implement candidate-route one-hot QUBO with normalized route objective and exactly-one penalty.
- Use a maintained simulated-annealing library only if licensing/install constraints are suitable; otherwise implement a small transparent annealing routine for this one-hot case, documenting it as classical simulated annealing.
- Set a reproducible seed, temperature schedule, iteration/time budget, and deterministic tie-breaker.
- Return selected candidate, objective breakdown, solver runtime, energy/sample and fallback reason.
- Add a classical weighted-cost selector over the same candidates as a diagnostic baseline.

**Done when:** optimizer never returns invalid route selection; seed reproduces the choice; timeout/failure cleanly falls back; route selection is unit-tested against small hand-computable cases.

### Phase 5 — Fair benchmarking and ablation

Run each OD/scenario/weight combination through all methods with identical inputs:

A. Classical fastest path (Dijkstra/A*).
B. Classical multi-objective shortest path or weighted candidate selection.
C. Quantum-inspired simulated-annealing candidate selector.

Record route validity, feasibility violations, time, CO₂/fuel estimate, congestion exposure, risk, route overlap, candidate count, graph size, algorithm wall-clock latency, provider/API latency, and failure/fallback count. Track any API costs separately from local compute score.

Use paired comparisons per trip, median and p95 latency, and impact deltas. Include 30–100 reproducible OD/scenario cases if time permits; at minimum include carefully designed hand cases that demonstrate (1) all objectives agree, (2) congestion creates a trade-off, (3) closure forces a detour, (4) data is missing/stale, and (5) solver timeout invokes fallback. Do not present one favorable trip as general evidence.

Ablate the QI solver: compare it with choosing the minimum `J_r` directly among the exact same candidates. In the one-hot formulation, direct argmin is an exact and trivial classical solution; annealing may add no quality advantage. Report this clearly. The defensible value of the prototype is demonstrating a QUBO/annealing workflow and trade-off modeling, not claiming annealing beats argmin for small candidate sets. To study a meaningful QUBO advantage later, expand to a compositional problem (e.g., select compatible route segments across multiple fleet trips with shared capacity/bottleneck constraints), then benchmark against a classical MILP/heuristic.

**Done when:** benchmark exports raw records, summary, charts/tables, environment details and a clear limitations section; rerunning with the same seed produces the same conclusions.

### Phase 6 — Streamlit UX and examiner-ready explanation

- Provide OD, vehicle/powertrain, preference weights, scenario (normal/peak/incident/stale), max detour/reliability constraints and seed controls.
- Show two route lines and a compact legend: classical fastest vs R2I/QI-selected route.
- Show aligned metric cards and a concise explanation: “selected because lower congestion/emissions, +X min, satisfies Y constraint.”
- Add an optimizer details expander: candidates considered, objective weights, normalized breakdown, annealing runtime, seed, fallback status, traffic source/time/confidence.
- Add a classical-vs-QI comparison table and benchmark page with runtime and paired outcomes.
- Avoid suggesting live traffic when only static/synthetic data is active.

**Done when:** an examiner can identify the baseline, selected route, why it was selected, what data was used, and whether the result came from annealing or fallback without reading code.

### Phase 7 — Qualcomm Cloud AI Playground integration (optional and bounded)

- Verify the hackathon’s intended use of the playground and available model/API access before development.
- If appropriate, use it only for a short explanation layer over already-computed structured metrics (e.g., plain-language route trade-off summary); do not ask an LLM to select the route or generate traffic facts.
- Send the minimum non-sensitive structured summary; no API keys, personal data, or unneeded precise user data.
- Bound timeout/retries and display deterministic local explanation if cloud inference is unavailable.
- Document model name/version, prompt/schema, measured latency, and whether the feature is optional.

**Done when:** disabling network access does not affect route correctness; the UI distinguishes computed route decision from generated narrative.

### Phase 8 — Packaging and final review

- Verify a clean setup from README in a fresh environment, with bundled map and offline scenarios.
- Keep secrets out of source control; provide `.env.example`/Streamlit secret template with placeholders only.
- Add an open-source license if the rules require one, setup/run instructions, source references, team credits, architecture, use cases, limitations, benchmark instructions and AI/cloud disclosure as required by the organizer.
- Prepare a 5-minute demo: problem → baseline → congestion/closure scenario → R2I route and metrics → benchmark evidence → limitations/impact.
- Record a backup demo video/screenshots and ensure offline mode works in the venue.

**Done when:** judge can clone, run, reproduce the demo and understand claims without credentials or external services.

## 8. Benchmark protocol and decision gates

Use these gates to avoid spending time on a solver that adds no value:

- **Gate A:** classical model is valid and metrics are consistent.
- **Gate B:** constraints and scenarios materially change valid route choices.
- **Gate C:** candidate set contains meaningful alternatives and is within latency budget.
- **Gate D:** QUBO encoding/decoding passes constraint checks on all fixtures.
- **Gate E:** compare QI selector against both fastest and classical multi-objective selector. If no measurable benefit at this scale, present it as a prototype/educational track and avoid superiority claims.
- **Gate F:** only integrate Cloud AI if it improves explanation quality and remains non-blocking.

Report target and measured values side by side; do not treat target thresholds as achieved results. Report API reliability/cost separately from algorithm runtime so an external request does not obscure local optimizer performance.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| “Quantum” overclaim | Name the exact classical simulated-annealing method; no quantum hardware/speedup claim. |
| One-hot QUBO is trivial | State this honestly; use it to validate encoding, then explore fleet-level shared-resource QUBO only if time allows. |
| Traffic API unavailable, restricted or costly | Offline deterministic scenarios; timeouts; optional integration; secret-free repository. |
| Traffic intervals do not align with OSM edges | Keep match radius/confidence; expose matched coverage; fall back to route-level delay or synthetic scenario visibly. |
| Emissions model is rough | Show assumptions/units; label estimates; calibrate by vehicle class and validate sensitivity. |
| External baselines use different data | Use the same graph/snapshot for algorithm comparison; show Google Maps separately as a product reference, not as the experimental control. |
| Optimizer chooses infeasible/poor sample | Independent route and QUBO feasibility checks; deterministic classical fallback. |
| Excessive runtime | Bound graph region, K candidates, annealing iterations and cloud calls; publish p50/p95 latency. |
| Unsupported hackathon/platform assumption | Verify exact official event brief, criteria, permitted APIs, submission format, and playground access before finalizing. |

## 10. Suggested team split

- **Graph/data owner:** graph coverage, traffic snapshot schema, bottleneck/incident scenarios, map matching, data provenance.
- **Optimization owner:** shared evaluator, baseline, candidate generation, QUBO, annealing, fallback and small-case validation.
- **Evaluation owner:** benchmark fixtures, paired metrics, runtime/cost logging, charts, statistical summary and limitations.
- **App/pitch owner:** dashboard comparison, examiner explanation, documentation, demo script, setup and offline rehearsal.

For a smaller team, combine evaluation with optimization and keep the cloud explanation feature last.

## 11. Submission artifacts

1. Runnable source + dependency lock/requirements.
2. README with setup/run instructions and offline demo path.
3. Architecture diagram and objective/QUBO explanation.
4. Benchmark data and results with configuration/seed.
5. Data sources, calibration assumptions, privacy and limitations.
6. Short demo video/slides plus live-demo fallback.
7. License and team/contact details if required by the organizer.

## 12. Current-code starting point

The implementation now includes a first candidate-route QUBO/annealing selector, offline traffic scenarios, route-risk/detour/time constraints, dashboard diagnostics, and a seeded paired benchmark. Remaining planned work includes improving reliability calibration, validating on a larger representative trip set, polishing presentation artifacts, and confirming any event-specific Qualcomm Playground requirements.

## Sources checked

- Infosys Global Hackathon page: https://www.infosys.com/infosys-global-hackathon.html — official page describes a working prototype, clear technical/impact documentation, architecture/use cases/impact analysis, SDG relevance, feasibility, impact, innovation and technical excellence. Confirm whether this is the exact event/track, since the screenshot’s ET-08 row may be from a separate brief.
- Qualcomm Cloud AI 100 playground overview: https://www.qualcomm.com/research/university-relations/developer-platforms-for-universities — positioned as an inference/model experimentation playground, which supports treating it as an optional explanation component rather than a routing solver.
- Routes API traffic model: https://developers.google.com/maps/documentation/routes/traffic-model — documents traffic-aware route duration.
- Traffic-aware polylines: https://developers.google.com/maps/documentation/routes/traffic_on_polylines — documents NORMAL/SLOW/TRAFFIC_JAM intervals and higher billing tier.
