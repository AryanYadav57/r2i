"""fleet/insights.py - Plain-language, map-anchored explanations of a plan comparison."""

from __future__ import annotations

from collections import Counter


def _fmt_money(x: float) -> str:
    return f"₹{abs(x):,.0f}"


def build_insights(net, scn, baseline: dict, r2i: dict, comparison: dict) -> list:
    b, r, d = comparison["baseline"], comparison["r2i"], comparison["delta"]
    out = []

    # 1. Headline
    co2_pct = 100 * d["co2_g"] / b["co2_g"] if b["co2_g"] else 0.0
    verb = "saves" if d["cost_inr"] <= 0 else "costs"
    out.append(dict(
        kind="headline",
        title=f"R2I {verb} {_fmt_money(d['cost_inr'])} and "
              f"{abs(d['co2_g']) / 1000:.2f} kg CO₂ today ({co2_pct:+.1f}% CO₂ vs distance-only planning)",
        detail=f"Fuel {b['fuel_l']:.2f} L → {r['fuel_l']:.2f} L, distance "
               f"{b['distance_km']:.1f} km → {r['distance_km']:.1f} km, idling "
               f"{b['idle_s'] / 60:.0f} → {r['idle_s'] / 60:.0f} min. Counting grid "
               f"electricity for the EVs, net CO₂ changes by "
               f"{(d['co2_g'] + d['grid_co2_g']) / 1000:+.2f} kg.",
    ))

    # 2. Electric vehicles absorb congested junctions
    def ev_share(plan):
        tot = sum(v["metrics"]["hot_junctions"] for v in plan["vehicles"])
        ev = sum(v["metrics"]["hot_junctions"] for v in plan["vehicles"] if v["fuel"] == "electric")
        return (ev / tot * 100 if tot else 0.0), ev, tot
    bs, _, _ = ev_share(baseline)
    rs, rev, rtot = ev_share(r2i)
    if rtot:
        out.append(dict(
            kind="ev_assignment",
            title=f"Electric vehicles take {rs:.0f}% of the busiest junction crossings (was {bs:.0f}%)",
            detail=f"{rev} of {rtot} crossings of the top-10% congested junctions are now driven "
                   "by EVs, which burn nothing while waiting.",
        ))

    # 3. Most avoided congested junction (by combustion vehicles)
    def ice_nodes(plan):
        return Counter(n for v in plan["vehicles"] if v["fuel"] != "electric" for n in v["_visited"])
    bn, rn = ice_nodes(baseline), ice_nodes(r2i)
    gain = {n: (bn[n] - rn.get(n, 0)) * net.idle_s[n] for n in bn if bn[n] > rn.get(n, 0)}
    if gain:
        n = max(gain, key=gain.get)
        lat, lon = net.coords(n)
        out.append(dict(
            kind="avoided_junction", lat=lat, lon=lon,
            title=f"Combustion vehicles skip a congested junction {bn[n] - rn.get(n, 0)}× today",
            detail=f"Congestion score {net.congestion[n]:.2f}, about {net.idle_s[n]:.0f} s of "
                   "idling per crossing.",
        ))

    # 4. Payload-aware stop order
    best = max(r2i["vehicles"], default=None,
               key=lambda v: v["objective_before_reorder"] - v["objective_after_reorder"])
    if best and best["objective_before_reorder"] - best["objective_after_reorder"] > 0.5:
        g = best["objective_before_reorder"] - best["objective_after_reorder"]
        s0 = best["stops"][0]
        out.append(dict(
            kind="payload_order", lat=s0["lat"], lon=s0["lon"], vehicle_id=best["id"],
            title=f"{best['id']} re-orders its stops for its load: {g:.0f} g CO₂-eq saved",
            detail="Heavier parcels are dropped earlier when that shortens the distance "
                   "driven fully loaded, without making any delivery late.",
        ))

    # 5. Service level
    if abs(d["on_time_pct"]) >= 0.5 or b["orders_served"] != r["orders_served"]:
        out.append(dict(
            kind="service",
            title=f"On-time {b['on_time_pct']:.0f}% → {r['on_time_pct']:.0f}%, "
                  f"orders served {b['orders_served']} → {r['orders_served']}",
            detail="Both plans use the same vehicles, capacities and delivery windows.",
        ))
    return out
