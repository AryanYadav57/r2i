"""Small, deterministic QUBO + simulated-annealing selector for route candidates.

This is a classical heuristic inspired by quantum optimization formulations; it
does not execute on quantum hardware. Each binary variable selects one already
valid candidate route, so path connectivity is preserved by construction.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any


def build_one_hot_qubo(scores: list[float], penalty: float | None = None) -> dict[tuple[int, int], float]:
    """Return upper-triangular Q for E(x)=sum Qij xi xj, exactly-one penalty."""
    if not scores:
        raise ValueError("At least one candidate score is required")
    bound = max(1.0, max(scores) - min(scores))
    lam = float(penalty if penalty is not None else bound + 1.0)
    if lam <= bound:
        raise ValueError("One-hot penalty must exceed the objective score range")
    qubo: dict[tuple[int, int], float] = {}
    # lambda * (sum(x)-1)^2 = -lambda*sum(x) + 2lambda*sum(i<j)xi*xj + constant
    for i, score in enumerate(scores):
        qubo[(i, i)] = float(score) - lam
        for j in range(i + 1, len(scores)):
            qubo[(i, j)] = 2.0 * lam
    return qubo


def _energy(bits: list[int], qubo: dict[tuple[int, int], float]) -> float:
    return sum(value * bits[i] * bits[j] for (i, j), value in qubo.items())


def solve_route_qubo(scores: list[float], *, seed: int = 42, iterations: int = 1200,
                     timeout_s: float = 0.05) -> dict[str, Any]:
    """Solve route one-hot QUBO with bounded single-bit simulated annealing.

    Since this special one-hot problem has a trivial exact classical solution,
    compare annealing's sample with exact argmin and return the better feasible
    state. The result reports both so benchmark claims remain honest.
    """
    started = time.perf_counter()
    qubo = build_one_hot_qubo(scores)
    rng = random.Random(seed)
    n = len(scores)
    bits = [0] * n
    bits[rng.randrange(n)] = 1
    current = _energy(bits, qubo)
    best_bits, best_energy = bits[:], current
    for step in range(max(1, int(iterations))):
        if time.perf_counter() - started >= timeout_s:
            break
        index = rng.randrange(n)
        candidate = bits[:]
        candidate[index] ^= 1
        energy = _energy(candidate, qubo)
        fraction = step / max(1, iterations - 1)
        temperature = max(1e-4, 1.0 - fraction)
        if energy < current or rng.random() < math.exp(min(0.0, (current - energy) / temperature)):
            bits, current = candidate, energy
        if current < best_energy:
            best_bits, best_energy = bits[:], current

    chosen = [i for i, bit in enumerate(best_bits) if bit]
    feasible = len(chosen) == 1
    annealed_index = chosen[0] if feasible else None
    exact_index = min(range(n), key=lambda i: (scores[i], i))
    # One-hot QUBO is exactly equivalent to selecting argmin. Exact safeguard
    # preserves a valid, optimal answer even if the bounded heuristic misses.
    selected_index = annealed_index if feasible and scores[annealed_index] <= scores[exact_index] else exact_index
    return {
        "selected_index": selected_index,
        "annealed_index": annealed_index,
        "annealed_feasible": feasible,
        "qubo_energy": _energy([int(i == selected_index) for i in range(n)], qubo),
        "solver": "Simulated annealing (classical, QUBO)",
        "seed": int(seed),
        "iterations": int(iterations),
        "runtime_ms": (time.perf_counter() - started) * 1000,
        "fallback": not feasible or annealed_index != selected_index,
        "classical_argmin_index": exact_index,
    }
