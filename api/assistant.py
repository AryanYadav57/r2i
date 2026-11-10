"""
api/assistant.py - "Ask AI": Claude with tools that call the R2I engine.

A manual tool loop (not the beta tool runner) because the route geometry each
tool produces is returned to the web app as map artifacts alongside the answer.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable

MODEL = "claude-opus-5-5"
MAX_TURNS = 6
VEHICLES = ["ICE", "EV", "van_diesel", "van_ev", "3w_ev", "2w_petrol", "car_petrol", "car_ev"]

SYSTEM = """You are the assistant inside Route-to-Impact (R2I), an eco-routing and fleet
planning demo for south-east Bengaluru (road network roughly 12.89-12.98 N, 77.58-77.67 E:
Koramangala, HSR Layout, Indiranagar, BTM, Ejipura, Domlur).

R2I predicts idling at junctions from OpenStreetMap structure (streets meeting, signals,
road class) and routes to minimise tailpipe CO2 plus alpha x time, compared with the
shortest-distance route. EVs have zero tailpipe CO2, so their best route is the fastest.

Use the tools for every number you state; never invent figures. To compare a trip between
named places, call find_place for each, then compare_route. Answer in 2-5 short sentences
or a compact list, lead with the result, and say figures are modelled estimates when you
quote CO2, fuel or cost. If a place is outside the covered area, say so."""

TOOLS = [
    {
        "name": "find_place",
        "description": "Geocode a place name in Bengaluru. Returns up to 3 matches with lat/lon.",
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                         "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "compare_route",
        "description": ("Compare the shortest-distance route with the R2I eco-route between two "
                        "points for a vehicle. Returns distance, time, idling, CO2, fuel/energy "
                        "and cost for both, plus the most congested junctions R2I avoids. The "
                        "route is drawn on the user's map."),
        "strict": True,
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["origin_lat", "origin_lon", "dest_lat", "dest_lon", "vehicle", "alpha"],
            "properties": {
                "origin_lat": {"type": "number"}, "origin_lon": {"type": "number"},
                "dest_lat": {"type": "number"}, "dest_lon": {"type": "number"},
                "vehicle": {"type": "string", "enum": VEHICLES},
                "alpha": {"type": ["number", "null"],
                          "description": "grams of CO2 one second is worth; null for default (1)"},
            },
        },
    },
    {
        "name": "fleet_summary",
        "description": ("Results of the demo fleet plan (one dark store, 70 orders, 7 vehicles): "
                        "distance-only planning vs R2I planning totals and key insights."),
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}, "required": []},
    },
    {
        "name": "vehicle_classes",
        "description": "Vehicle classes R2I models, with emission/energy factors and payload.",
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}, "required": []},
    },
]


def _r(x, n=1):
    return round(float(x), n)


def _route_summary(res: dict) -> dict:
    def m(x):
        return {"distance_km": _r(x["distance_km"], 2),
                "time_min": _r((x["travel_time_s"] + x["total_idle_s"]) / 60),
                "idle_min": _r(x["total_idle_s"] / 60), "co2_g": _r(x["total_co2_g"]),
                "fuel_ml": _r(x["fuel_ml"]), "energy_kwh": _r(x["energy_kwh"], 2),
                "cost_inr": _r(x["cost_inr"])}
    return {"shortest": m(res["baseline"]["metrics"]), "r2i": m(res["r2i"]["metrics"]),
            "routes_differ": res["diverged"],
            "avoided_junctions": [{"congestion": _r(a["congestion"], 2), "idle_s": _r(a["idle_s"])}
                                  for a in res["avoided"][:5]]}


def run(client, messages: list, tools_impl: dict[str, Callable]) -> dict:
    """Run the tool loop. Returns {answer, artifacts}."""
    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    artifacts: list = []
    for _ in range(MAX_TURNS):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=convo,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            return {"answer": "I can't help with that one. Try asking about routes, junctions "
                              "or the delivery fleet.", "artifacts": artifacts}
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return {"answer": text.strip() or "(no answer)", "artifacts": artifacts}

        convo.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            try:
                out, artifact = tools_impl[block.name](dict(block.input))
                if artifact:
                    artifacts.append(artifact)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out)})
            except Exception as exc:   # report to the model, never crash the request
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"Error: {exc}", "is_error": True})
        convo.append({"role": "user", "content": results})
    return {"answer": "That needed too many steps. Try a more specific question.",
            "artifacts": artifacts}


def make_tools(compare: Callable, geocode: Callable, fleet: Callable, vehicles: Callable) -> dict:
    """Bind tool names to engine calls. compare(req_dict) returns the /route/compare body."""

    def compare_route(inp):
        missing = {"origin_lat", "origin_lon", "dest_lat", "dest_lon", "vehicle"} - set(inp)
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        if inp["vehicle"] not in VEHICLES:
            raise ValueError(f"unknown vehicle {inp['vehicle']!r}")
        body = compare(inp)
        artifact = {"type": "route", "vehicle": inp["vehicle"], "baseline": body["baseline"],
                    "r2i": body["r2i"], "avoided": body["avoided"],
                    "origin": [inp["origin_lon"], inp["origin_lat"]],
                    "dest": [inp["dest_lon"], inp["dest_lat"]]}
        return _route_summary(body), artifact

    def find_place(inp):
        return geocode(str(inp.get("query", "")))[:3], None

    def fleet_summary(_):
        d = fleet()
        return {"comparison": d["comparison"], "insights": [i["title"] for i in d["insights"]]}, None

    return {"compare_route": compare_route, "find_place": find_place,
            "fleet_summary": fleet_summary, "vehicle_classes": lambda _: (vehicles(), None)}


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (Qualcomm AI Playground / Cirrascale Inference Cloud)
# ---------------------------------------------------------------------------
INFERENCE_MODEL = os.environ.get("INFERENCE_CLOUD_MODEL", "Llama-3.3-70B")


def _openai_tools() -> list:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in TOOLS]


def run_inference_cloud(endpoint: str, api_key: str, messages: list, tools_impl: dict) -> dict:
    """Same tool loop as run(), over an OpenAI-compatible /chat/completions API."""
    import requests

    convo = [{"role": "system", "content": SYSTEM}] + [
        {"role": m["role"], "content": m["content"]} for m in messages]
    artifacts: list = []
    for _ in range(MAX_TURNS):
        r = requests.post(f"{endpoint.rstrip('/')}/chat/completions", timeout=90,
                          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                          json={"model": INFERENCE_MODEL, "max_tokens": 1024, "temperature": 0.2,
                                "messages": convo, "tools": _openai_tools()})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls") or parse_text_tool_calls(msg.get("content") or "")
        if not calls:
            return {"answer": clean_answer(msg.get("content") or "") or "(no answer)", "artifacts": artifacts}
        # One call per assistant message: the provider rejects messages carrying several tool calls.
        for call in calls:
            convo.append({"role": "assistant", "content": "", "tool_calls": [call]})
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
                out, artifact = tools_impl[fn["name"]](args)
                if artifact:
                    artifacts.append(artifact)
                content = json.dumps(out)
            except Exception as exc:   # report to the model, never crash the request
                content = f"Error: {exc}"
            convo.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": content})
    return {"answer": "That needed too many steps. Try a more specific question.", "artifacts": artifacts}


_TOKEN = re.compile(r"<\|[a-z_]+\|>")


def parse_text_tool_calls(text: str) -> list:
    """Extract Llama-style text tool calls: <|python_tag|>{"name": ..., "parameters": ...}."""
    calls = []
    for chunk in text.split("<|python_tag|>")[1:]:
        chunk = _TOKEN.split(chunk)[0].strip()
        try:
            obj = json.loads(chunk)
        except ValueError:
            continue            # e.g. a code snippet, not a call
        name = obj.get("name") if isinstance(obj, dict) else None
        if name in {t["name"] for t in TOOLS}:
            params = obj.get("parameters", obj.get("arguments", {}))
            args = params if isinstance(params, str) else json.dumps(params)
            calls.append({"id": f"text-{len(calls)}", "type": "function", "function": {"name": name, "arguments": args}})
    return calls


def clean_answer(text: str) -> str:
    """Drop model control tokens and anything after a stray tool tag."""
    return _TOKEN.sub("", text.split("<|python_tag|>")[0]).strip()
