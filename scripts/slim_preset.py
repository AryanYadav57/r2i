"""
Shrink the fleet preset for the web: trajectories become delta-encoded integers
(1e-5 degree and 0.1 s units) and other floats are rounded. The web app decodes
`traj` back into [lon, lat, t] triples (see web/src/lib/data.ts: decodeFleet).

Usage:  python scripts/slim_preset.py [path/to/preset.json]
"""

import json
import os
import sys

DEFAULT = os.path.join(os.path.dirname(__file__), "..", "web", "public", "scenarios", "preset.json")


def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [_round(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    return obj


def encode_traj(traj):
    out, prev = [], (0, 0, 0)
    for lon, lat, t in traj:
        cur = (round(lon * 1e5), round(lat * 1e5), round(t * 10))
        out.extend(c - p for c, p in zip(cur, prev))
        prev = cur
    return out


def slim(preset: dict) -> dict:
    for plan in ("baseline", "r2i"):
        for v in preset[plan]["vehicles"]:
            v["traj"] = encode_traj(v.pop("trajectory"))
            v["events"] = [e for e in v["events"] if e["type"] != "idle" or e.get("seconds", 0) >= 8]
    preset = _round(preset)
    preset["encoding"] = "traj-delta-v1"
    return preset


def main(path=DEFAULT):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("encoding") == "traj-delta-v1":
        print("already slim")
        return
    before = os.path.getsize(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(slim(data), fh, separators=(",", ":"))
    print(f"{before // 1024} KB -> {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main(*sys.argv[1:])
