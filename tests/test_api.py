"""API contract tests against a synthetic grid (no OSM download)."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.test_fleet import grid_graph

STEP = 200 / 111_000
A = {"lat": 12.93, "lon": 77.6}
B = {"lat": 12.93 + 6 * STEP, "lon": 77.6 + 6 * STEP}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(graph=grid_graph())) as c:
        yield c


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_graph_nodes(client):
    body = client.get("/graph/nodes").json()
    assert body["count"] == 49
    lon, lat, score, signal = body["nodes"][0]
    assert 0 <= score <= 1 and signal in (0, 1)


def test_vehicles_listed(client):
    keys = {v["key"] for v in client.get("/vehicles").json()}
    assert {"van_diesel", "3w_ev", "car_petrol"} <= keys


def test_route_compare(client):
    r = client.post("/route/compare", json={"origin": A, "dest": B, "vehicle": "ICE"})
    assert r.status_code == 200
    body = r.json()
    for k in ("baseline", "r2i"):
        assert len(body[k]["path"]) >= 2
        assert body[k]["metrics"]["total_co2_g"] > 0
    assert isinstance(body["avoided"], list) and "diverged" in body


def test_route_compare_alpha_changes_result(client):
    lo = client.post("/route/compare", json={"origin": A, "dest": B, "vehicle": "ICE", "alpha": 0}).json()
    hi = client.post("/route/compare", json={"origin": A, "dest": B, "vehicle": "ICE", "alpha": 50}).json()
    assert lo["r2i"]["metrics"]["total_co2_g"] <= hi["r2i"]["metrics"]["total_co2_g"] + 1e-6


def test_route_compare_unknown_vehicle_is_422(client):
    r = client.post("/route/compare", json={"origin": A, "dest": B, "vehicle": "zeppelin"})
    assert r.status_code == 422


def test_route_sweep(client):
    body = client.post("/route/sweep", json={"origin": A, "dest": B, "vehicle": "ICE",
                                             "alphas": [0, 1, 10]}).json()
    assert [p["alpha"] for p in body["points"]] == [0, 1, 10]


def test_route_explore(client):
    body = client.post("/route/explore", json={"origin": A, "dest": B, "objective": "car_petrol"}).json()
    assert 2 <= len(body["visited"]) <= 49
    assert body["path"][0] == body["visited"][0][:2]


def test_fleet_plan_generated(client):
    r = client.post("/fleet/plan", json={
        "hub": {"lat": 12.93 + 3 * STEP, "lon": 77.6 + 3 * STEP},
        "vehicles": ["van_diesel", "3w_ev"], "n_orders": 6, "seed": 1,
        "radius_m": 1500, "time_limit_s": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["comparison"]["r2i"]["orders_served"] == 6
    assert body["r2i"]["vehicles"][0]["trajectory"]


def test_fleet_plan_explicit_orders(client):
    r = client.post("/fleet/plan", json={
        "hub": A, "vehicles": ["van_ev"], "time_limit_s": 1,
        "orders": [{"lat": B["lat"], "lon": B["lon"], "weight_kg": 5,
                    "tw_start_s": 32400, "tw_end_s": 46800}]})
    assert r.json()["r2i"]["vehicles"][0]["stops"][0]["order_id"] == "O01"


@pytest.mark.parametrize("bad", [
    {"orders": [{"lat": B["lat"], "lon": B["lon"], "weight_kg": 5, "tw_start_s": 40000, "tw_end_s": 35000}]},
    {"shift_start_s": 46800, "shift_end_s": 32400},
    {"shift_end_s": 90000},
])
def test_fleet_plan_rejects_invalid_times(client, bad):
    body = {"hub": A, "vehicles": ["van_ev"], "time_limit_s": 1, "n_orders": 3, **bad}
    assert client.post("/fleet/plan", json=body).status_code == 422
