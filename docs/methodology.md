# Mathematical Methodology
## Route-to-Impact (R2I) · docs/methodology.md

> **Status:** Phase 13 Deliverable — Fill after Phase 12 completes.
> This document must contain all mathematical derivations and algorithm proofs.

---

## 1. Congestion Score Derivation

S(v) = clip( (k_v * w_d + I_signal * w_s + W_class * w_c) / max_possible, 0, 1 )

### Parameter Definitions

| Symbol | Variable | Default | Rationale |
|---|---|---|---|
| k_v | node_degree | G.degree(v) | Intersection complexity |
| I_signal | is_signal | {0, 1} | Binary traffic signal tag |
| W_class | highway_class_weight | [0.1, 1.0] | Road tier congestion |
| w_d | DEGREE_WEIGHT | 0.5 | Dominant contributor |
| w_s | SIGNAL_WEIGHT | 0.3 | Secondary contributor |
| w_c | ROAD_CLASS_WEIGHT | 0.2 | Tertiary contributor |

### Normalisation

max_possible = 8 * w_d + 1 * w_s + 1 * w_c
             = 8 * 0.5 + 0.3 + 0.2 = 4.5

(Assuming max realistic node degree = 8)

---

## 2. Edge Cost Formula

W_edge(e) = L_e * E_cruise + T_idle(e) * E_idle + alpha * T_travel(e)

### Derivation

[To be completed in Phase 13]

---

## 3. Algorithmic Complexity

Dijkstra with Fibonacci heap: O(|E| + |V| log |V|)
For a 5 km Koramangala grid (~1200 nodes, ~3500 edges): sub-200ms expected.

---

*Document to be finalised in Phase 13.*
