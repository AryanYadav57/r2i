"""
Precompute static demo data for the web app (loads instantly, no API needed).

  web/public/scenarios/preset.json   fleet preset: both plans, trajectories, insights
  web/public/scenarios/nodes.json    congestion per graph node
  web/public/scenarios/race.json     one baseline-vs-R2I trip for the race scene

Usage:  python scripts/precompute_scenarios.py
"""

import json
import os

from fastapi.testclient import TestClient

from api.main import create_app

OUT = os.path.join(os.path.dirname(__file__), "..", "web", "public", "scenarios")
RACE_VEHICLE = "van_diesel"
RACE_CANDIDATES = 40


def best_race(c, nodes, seed=7):
    """Pick the seeded 3-7 km trip where R2I saves the most CO2."""
    import math
    import random
    rng = random.Random(seed)
    best, best_gain = None, -1.0
    for _ in range(RACE_CANDIDATES):
        a, b = rng.sample(nodes, 2)
        km = math.dist(a[:2], b[:2]) * 108
        if not 3 <= km <= 7:
            continue
        req = {"origin": {"lon": a[0], "lat": a[1]}, "dest": {"lon": b[0], "lat": b[1]},
               "vehicle": RACE_VEHICLE}
        r = c.post("/route/compare", json=req)
        if r.status_code != 200:
            continue
        body = r.json()
        gain = -body["delta"]["total_co2_g"]
        if body["diverged"] and gain > best_gain:
            best, best_gain = dict(body, request=req), gain
    return best


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    print(f"{name}: {os.path.getsize(path) // 1024} KB")


def main():
    os.makedirs(OUT, exist_ok=True)
    preset = os.path.join(OUT, "preset.json")
    if os.path.exists(preset):
        os.remove(preset)          # force a fresh plan
    with TestClient(create_app()) as c:
        nodes = c.get("/graph/nodes").json()
        scores = sorted(n[2] for n in nodes["nodes"])
        cut = scores[int(0.85 * (len(scores) - 1))]
        hot = [[round(n[0], 5), round(n[1], 5), n[2], n[3]] for n in nodes["nodes"] if n[2] >= cut]
        dump("nodes.json", {"count": len(hot), "fields": nodes["fields"], "nodes": hot})
        dump("race.json", best_race(c, nodes["nodes"]))
        from scripts.slim_preset import slim
        dump("preset.json", slim(c.get("/fleet/preset").json()))


if __name__ == "__main__":
    main()
