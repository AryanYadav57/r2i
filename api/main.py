"""
api/main.py - FastAPI service for the R2I web app.

Run:  uvicorn api.main:app --reload
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api import assistant
from api.schemas import (AskRequest, CompareRequest, ExploreRequest, FleetPlanRequest,
                         SweepRequest)
from r2i.evaluation.experiments import PatchedConfig
from r2i.fleet import RoadNetwork, generate_scenario, plan_fleet, preset_scenario
from r2i.fleet.model import FleetVehicle, Hub, Order, Scenario
from r2i.models.vehicle import VEHICLE_SPECS, make_vehicle
from r2i.routing.baseline import RouteNotFoundError
from r2i.routing.router import compare_routes

def _load_dotenv(path=os.path.join(os.path.dirname(__file__), "..", ".env")):
    """Minimal .env loader (KEY=VALUE lines); real environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

PRESET_PATH = os.path.join(os.path.dirname(__file__), "..", "web", "public", "scenarios",
                           "preset.json")


def _default_llm():
    import anthropic
    return anthropic.Anthropic()


def create_app(graph=None, llm=None) -> FastAPI:
    """graph: preloaded routing graph (tests); llm: zero-arg factory for a Claude client."""
    llm = llm or _default_llm
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        G = graph
        if G is None:
            from r2i.routing.router import load_routing_graph
            G = load_routing_graph()
        state.update(G=G, net=RoadNetwork(G), lock=threading.Lock())
        yield

    app = FastAPI(title="R2I API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("R2I_CORS", "http://localhost:5173").split(","),
        allow_methods=["*"], allow_headers=["*"])

    def net() -> RoadNetwork:
        return state["net"]

    def node_of(p) -> int:
        return net().nearest(p.lat, p.lon)

    def vehicle(key: str):
        try:
            return make_vehicle(key)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def coords(path_ids):
        G = state["G"]
        return [[float(G.nodes[n]["x"]), float(G.nodes[n]["y"])] for n in path_ids]

    def compare(req, alpha=None):
        n = net()
        o, d = n.node_ids[node_of(req.origin)], n.node_ids[node_of(req.dest)]
        cfg = PatchedConfig({} if alpha is None else {"ALPHA": alpha})
        veh = vehicle(req.vehicle)
        with state["lock"]:   # compare_routes stamps weights onto the shared graph
            try:
                return compare_routes(state["G"], o, d, veh, cfg)
            except RouteNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "nodes": net().n}

    @app.get("/graph/nodes")
    def graph_nodes():
        n = net()
        nodes = [[round(float(n.lon[i]), 6), round(float(n.lat[i]), 6),
                  round(float(n.congestion[i]), 3), int(n.is_signal[i])] for i in range(n.n)]
        return {"count": n.n, "fields": ["lon", "lat", "congestion", "signal"], "nodes": nodes}

    @app.get("/vehicles")
    def vehicles():
        return [dict(key=s.key, label=s.label, fuel=s.fuel, capacity_kg=s.capacity_kg,
                     cruise_co2_g_km=s.cruise_co2_g_km, kwh_per_km=s.kwh_per_km,
                     battery_kwh=s.battery_kwh) for s in VEHICLE_SPECS.values()]

    def compare_body(req: CompareRequest) -> dict:
        res = compare(req, req.alpha)
        G = state["G"]
        avoided = [dict(lon=float(G.nodes[a]["x"]), lat=float(G.nodes[a]["y"]),
                        congestion=float(G.nodes[a].get("congestion_score", 0.0)),
                        idle_s=float(G.nodes[a].get("idle_time_s", 0.0)))
                   for a in res["avoided_nodes"]]
        avoided.sort(key=lambda a: -a["congestion"])
        return dict(
            baseline=dict(path=coords(res["baseline_path"]), metrics=res["baseline"]),
            r2i=dict(path=coords(res["r2i_path"]), metrics=res["r2i"]),
            delta=res["delta"], diverged=res["diverged"], avoided=avoided[:20])

    @app.post("/route/compare")
    def route_compare(req: CompareRequest):
        return compare_body(req)

    @app.post("/route/sweep")
    def route_sweep(req: SweepRequest):
        pts = []
        for a in req.alphas:
            m = compare(req, a)["r2i"]
            pts.append(dict(alpha=a, time_s=m["travel_time_s"] + m["total_idle_s"],
                            co2_g=m["total_co2_g"], distance_km=m["distance_km"],
                            cost_inr=m["cost_inr"]))
        return {"points": pts}

    @app.post("/route/explore")
    def route_explore(req: ExploreRequest):
        if req.objective != "distance" and req.objective not in VEHICLE_SPECS:
            raise HTTPException(422, f"unknown objective {req.objective!r}")
        n = net()
        order, path = n.explore(node_of(req.origin), node_of(req.dest), req.objective,
                                req.max_nodes)

        def pt(i):
            return [round(float(n.lon[i]), 6), round(float(n.lat[i]), 6)]

        return {"visited": [pt(i) + [round(float(n.congestion[i]), 3)] for i in order],
                "path": [pt(i) for i in path]}

    @app.get("/geocode")
    def geocode(q: str):
        try:
            return _geocode(q.strip())
        except Exception as exc:   # upstream outage should not 500 the app
            raise HTTPException(502, f"geocoder unavailable: {exc}") from exc

    @app.get("/fleet/preset")
    def fleet_preset():
        if os.path.exists(PRESET_PATH):
            with open(PRESET_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        if "preset" not in state:
            state["preset"] = plan_fleet(net(), preset_scenario(net()))
        return state["preset"]

    def compare_tool(inp):
        alpha = inp.get("alpha")
        return compare_body(CompareRequest(
            origin={"lat": inp["origin_lat"], "lon": inp["origin_lon"]},
            dest={"lat": inp["dest_lat"], "lon": inp["dest_lon"]},
            vehicle=inp["vehicle"], alpha=alpha))

    @app.post("/ask")
    def ask(req: AskRequest):
        cloud_key = os.environ.get("INFERENCE_CLOUD_API_KEY")
        if cloud_key:
            import requests
            tools = assistant.make_tools(compare_tool, _geocode, fleet_preset, vehicles)
            try:
                return assistant.run_inference_cloud(
                    os.environ.get("INFERENCE_CLOUD_ENDPOINT", "https://aisuite.cirrascale.com/apis/v2"),
                    cloud_key, [t.model_dump() for t in req.messages], tools)
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else 502
                raise HTTPException(503 if code in (401, 403) else 502, f"Ask AI upstream error ({code})") from exc
            except requests.RequestException as exc:
                raise HTTPException(502, "Ask AI upstream unreachable") from exc
        try:
            client = llm()
        except Exception as exc:
            raise HTTPException(503, f"Ask AI is not configured (set ANTHROPIC_API_KEY): {exc}") from exc

        tools = assistant.make_tools(compare_tool, _geocode, fleet_preset, vehicles)
        try:
            return assistant.run(client, [t.model_dump() for t in req.messages], tools)
        except Exception as exc:
            import anthropic
            if isinstance(exc, anthropic.AuthenticationError):
                raise HTTPException(503, "Ask AI is not configured: invalid credentials") from exc
            if isinstance(exc, anthropic.RateLimitError):
                raise HTTPException(429, "Ask AI is busy, try again shortly") from exc
            if isinstance(exc, (anthropic.APIConnectionError, anthropic.APIStatusError)):
                raise HTTPException(502, f"Ask AI upstream error: {exc}") from exc
            if isinstance(exc, anthropic.AnthropicError):   # e.g. no credentials found
                raise HTTPException(503, f"Ask AI is not configured: {exc}") from exc
            if isinstance(exc, TypeError) and "authentication" in str(exc):
                raise HTTPException(503, "Ask AI is not configured: set ANTHROPIC_API_KEY") from exc
            raise

    @app.post("/fleet/plan")
    def fleet_plan(req: FleetPlanRequest):
        for k in req.vehicles:
            if k not in VEHICLE_SPECS:
                raise HTTPException(422, f"unknown vehicle class {k!r}")
        n = net()
        if req.orders:
            hub_node = node_of(req.hub)
            hlat, hlon = n.coords(hub_node)
            orders = []
            for i, o in enumerate(req.orders):
                node = n.nearest(o.lat, o.lon)
                lat, lon = n.coords(node)
                orders.append(Order(f"O{i + 1:02d}", lat, lon, node, o.weight_kg,
                                    o.tw_start_s, o.tw_end_s))
            counts: dict = {}
            fleet = []
            for k in req.vehicles:
                counts[k] = counts.get(k, 0) + 1
                fleet.append(FleetVehicle.of(f"{k}-{counts[k]}", k,
                                             shift_start_s=req.shift_start_s,
                                             shift_end_s=req.shift_end_s))
            scn = Scenario(Hub(hlat, hlon, hub_node), orders, fleet)
        else:
            scn = generate_scenario(n, req.n_orders, req.seed, req.hub.lat, req.hub.lon,
                                    req.vehicles, req.radius_m,
                                    shift_end_h=req.shift_end_s // 3600)
        try:
            return plan_fleet(n, scn, req.time_limit_s)
        except Exception as exc:   # solver rejects an impossible model
            raise HTTPException(422, f"could not plan this scenario: {exc}") from exc

    return app


@lru_cache(maxsize=512)
def _geocode(q: str):
    import requests
    if not q:
        return []
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if key:   # Google Geocoding (biased to Bengaluru); falls back to OSM Nominatim
        try:
            g = requests.get("https://maps.googleapis.com/maps/api/geocode/json", timeout=8, params={
                "address": q, "region": "in", "bounds": "12.8,77.45|13.1,77.8", "key": key}).json()
            if g.get("status") == "OK":
                return [dict(label=x["formatted_address"], lat=x["geometry"]["location"]["lat"],
                             lon=x["geometry"]["location"]["lng"]) for x in g["results"][:5]]
        except requests.RequestException:
            pass
    r = requests.get("https://nominatim.openstreetmap.org/search", timeout=8,
                     headers={"User-Agent": "r2i-eco-router/0.2 (open-source demo)"},
                     params={"q": q, "format": "json", "limit": 5, "countrycodes": "in",
                             "viewbox": "77.45,13.1,77.8,12.8", "bounded": 1})
    r.raise_for_status()
    return [dict(label=x["display_name"], lat=float(x["lat"]), lon=float(x["lon"]))
            for x in r.json()]


app = create_app()
