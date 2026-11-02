
import networkx as nx
import os
import requests
import ast
import re
import math
from pathlib import Path

# --- BANGALORE CALIBRATION CONSTANTS ---
FUEL_PRICE_INR_PER_LITER = 105.0
PETROL_CARBON_PER_ML = 2.31
PM25_PER_ML_PETROL = 0.05
TREE_CO2_PER_YEAR = 21000
CO2_PER_DAY_TREE = TREE_CO2_PER_YEAR / 365
INDIA_GRID_CO2_G_PER_KWH = 675.0  # CEA CO2 Baseline Database, Version 22.0 (FY 2025-26)
EV_KWH_PER_KM = 0.18
EV_IDLE_KWH_PER_MIN = 0.008
EV_PRICE_INR_PER_KWH = 8.0  # illustrative tariff assumption; configure for local tariffs
IDLE_FUEL_ML_PER_MIN = 25.0

ROAD_SPEED_KMH = {
    "motorway": 60, "motorway_link": 40, "trunk": 50, "trunk_link": 35,
    "primary": 40, "primary_link": 30, "secondary": 35, "secondary_link": 25,
    "tertiary": 30, "tertiary_link": 22, "unclassified": 25,
    "residential": 25, "living_street": 12, "service": 15, "track": 12,
    "busway": 25,
}
ROAD_CONGESTION = {
    "motorway": 0.12, "motorway_link": 0.16, "trunk": 0.18, "trunk_link": 0.20,
    "primary": 0.30, "primary_link": 0.28, "secondary": 0.24,
    "secondary_link": 0.22, "tertiary": 0.17, "tertiary_link": 0.16,
    "unclassified": 0.13, "residential": 0.12, "living_street": 0.07,
    "service": 0.10, "track": 0.08, "busway": 0.20,
}


def _first_value(value):
    """Normalize OSM GraphML values that may be scalar, list, or list text."""
    if isinstance(value, (list, tuple, set)):
        return next(iter(value), None)
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (list, tuple)):
                return next(iter(parsed), None)
        except (ValueError, SyntaxError):
            pass
    return value


def _number(value, default=0.0):
    value = _first_value(value)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else default


def estimate_edge_metrics(edge_data, vehicle_type="ICE", traffic_multiplier=1.0):
    """Estimate time, energy, and CO2 for one OSM road edge.

    OSMnx GraphML stores many numeric fields as strings and can store multiple
    values as lists. Missing speed/congestion values are estimated from the
    OSM highway class rather than treating every road identically.
    """
    distance_km = max(0.0, _number(edge_data.get("length"))) / 1000.0
    highway = str(_first_value(edge_data.get("highway", "residential"))).lower()
    speed_kmh = _number(edge_data.get("maxspeed"), ROAD_SPEED_KMH.get(highway, 25.0))
    if "mph" in str(edge_data.get("maxspeed", "")).lower():
        speed_kmh *= 1.60934
    speed_kmh = min(max(speed_kmh, 5.0), 100.0)

    base_time_min = (distance_km / speed_kmh) * 60.0
    default_congestion = ROAD_CONGESTION.get(highway, 0.12)
    congestion = _number(edge_data.get("idle_probability"), default_congestion)
    traffic = min(max(_number(traffic_multiplier, 1.0), 1.0), 2.5)
    congestion = min(max(congestion * traffic, 0.0), 0.85)
    idle_time_min = base_time_min * congestion * 1.5
    travel_time_min = base_time_min + idle_time_min

    is_ev = vehicle_type in {"EV", "Electric Car", "EV Scooter"}
    if is_ev:
        energy_kwh = distance_km * EV_KWH_PER_KM + idle_time_min * EV_IDLE_KWH_PER_MIN
        fuel_ml = 0.0
        carbon_g = energy_kwh * INDIA_GRID_CO2_G_PER_KWH
        cost_inr = energy_kwh * EV_PRICE_INR_PER_KWH
    else:
        profile = VEHICLE_PROFILES.get(vehicle_type, {"cruise": 40.0, "idle": IDLE_FUEL_ML_PER_MIN})
        fuel_ml = distance_km * profile.get("cruise", 40.0) + idle_time_min * profile.get("idle", IDLE_FUEL_ML_PER_MIN)
        energy_kwh = 0.0
        carbon_g = fuel_ml * PETROL_CARBON_PER_ML
        cost_inr = (fuel_ml / 1000.0) * FUEL_PRICE_INR_PER_LITER

    return {
        "distance_km": distance_km,
        "travel_time_min": travel_time_min,
        "fuel_ml": fuel_ml,
        "energy_kwh": energy_kwh,
        "carbon_g": carbon_g,
        "cost_inr": cost_inr,
    }


def _edge_options(graph, edge_data):
    return list(edge_data.values()) if graph.is_multigraph() else [edge_data]


def _traffic_multiplier_for_edge(graph, u, v, traffic_multiplier, traffic_segments):
    """Match Google traffic polyline sections to nearby OSM edge midpoints."""
    base_multiplier = min(max(_number(traffic_multiplier, 1.0), 1.0), 2.5)
    if not traffic_segments:
        return base_multiplier

    a, b = graph.nodes[u], graph.nodes[v]
    lat = (_number(a.get("y")) + _number(b.get("y"))) / 2.0
    lon = (_number(a.get("x")) + _number(b.get("x"))) / 2.0
    best_distance = float("inf")
    best_multiplier = base_multiplier
    for segment in traffic_segments:
        speed = segment.get("speed", "NORMAL")
        local_multiplier = {"NORMAL": 1.0, "SLOW": 1.6, "TRAFFIC_JAM": 2.2}.get(speed, 1.0)
        for point in segment.get("points", ()):
            point_lat, point_lon = point
            east = (float(point_lon) - lon) * 111_320 * math.cos(math.radians(lat))
            north = (float(point_lat) - lat) * 111_320
            distance = math.hypot(east, north)
            if distance < best_distance:
                best_distance = distance
                best_multiplier = max(base_multiplier, local_multiplier)
    return best_multiplier if best_distance <= 120.0 else base_multiplier


def _route_traffic_multiplier(route_points, traffic_multiplier, traffic_segments):
    """Estimate route delay from Google traffic intervals near candidate points."""
    fallback = min(max(_number(traffic_multiplier, 1.0), 1.0), 2.5)
    if not traffic_segments:
        return fallback
    severity = {"NORMAL": 1.0, "SLOW": 1.6, "TRAFFIC_JAM": 2.2}
    total = 0.0
    for lat, lon in route_points:
        nearest_distance = float("inf")
        nearest_multiplier = fallback
        for segment in traffic_segments:
            local_multiplier = severity.get(segment.get("speed", "NORMAL"), 1.0)
            for point_lat, point_lon in segment.get("points", ()):
                east = (float(point_lon) - lon) * 111_320 * math.cos(math.radians(lat))
                north = (float(point_lat) - lat) * 111_320
                distance = math.hypot(east, north)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_multiplier = max(fallback, local_multiplier)
        total += nearest_multiplier if nearest_distance <= 120.0 else fallback
    return total / max(len(route_points), 1)


def calculate_route_comparison(graph, source, target, vehicle_type="ICE", alpha=0.3, traffic_multiplier=1.0, traffic_segments=None):
    """Calculate fastest and lower-impact paths, accounting for parallel OSM edges."""
    alpha = min(max(float(alpha), 0.0), 1.0)

    def metrics_for(data, u, v):
        edge_multiplier = _traffic_multiplier_for_edge(graph, u, v, traffic_multiplier, traffic_segments)
        return estimate_edge_metrics(data, vehicle_type, edge_multiplier)

    def time_cost(data, u, v):
        return metrics_for(data, u, v)["travel_time_min"]

    def eco_cost(data, u, v):
        metrics = metrics_for(data, u, v)
        # The eco slider trades estimated travel time against estimated CO2.
        return alpha * metrics["travel_time_min"] + (1.0 - alpha) * metrics["carbon_g"] / 10.0

    def bundle_cost(u, v, edge_data, scorer):
        return min(scorer(data, u, v) for data in _edge_options(graph, edge_data))

    normal_path = nx.shortest_path(graph, source, target, weight=lambda u, v, data: bundle_cost(u, v, data, time_cost))
    eco_path = nx.shortest_path(graph, source, target, weight=lambda u, v, data: bundle_cost(u, v, data, eco_cost))

    def path_stats(path, scorer):
        totals = {"distance_km": 0.0, "travel_time_min": 0.0, "fuel_ml": 0.0, "energy_kwh": 0.0, "carbon_g": 0.0, "cost_inr": 0.0}
        for u, v in nx.utils.pairwise(path):
            alternatives = _edge_options(graph, graph.get_edge_data(u, v))
            selected = min(alternatives, key=lambda data: scorer(data, u, v))
            for key, value in metrics_for(selected, u, v).items():
                totals[key] += value
        return totals

    normal_stats = path_stats(normal_path, time_cost)
    eco_stats = path_stats(eco_path, eco_cost)
    savings = {
        "carbon_g": normal_stats["carbon_g"] - eco_stats["carbon_g"],
        "fuel_ml": normal_stats["fuel_ml"] - eco_stats["fuel_ml"],
        "energy_kwh": normal_stats["energy_kwh"] - eco_stats["energy_kwh"],
        "money_inr": normal_stats["cost_inr"] - eco_stats["cost_inr"],
        "time_diff": eco_stats["travel_time_min"] - normal_stats["travel_time_min"],
    }
    savings["tree_equiv"] = savings["carbon_g"] / CO2_PER_DAY_TREE
    return {
        "standard_path": normal_path,
        "eco_path": eco_path,
        "standard": normal_stats,
        "eco": eco_stats,
        "savings": savings,
    }


def calculate_external_route_comparison(start_coords, end_coords, vehicle_type="ICE", alpha=0.3, traffic_multiplier=1.0, traffic_segments=None):
    """Compare road-route alternatives for trips beyond the bundled graph.

    This fallback uses the public OSRM demo's candidate routes and applies the
    same time-versus-impact objective. Its emissions are distance-based
    estimates because this service does not return the local graph's segment
    attributes. A live Google traffic multiplier can adjust candidate times.
    Coordinates are (latitude, longitude); returned route geometry is Leaflet
    friendly (latitude, longitude).
    """
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    )
    response = requests.get(
        url,
        params={"alternatives": "3", "overview": "full", "geometries": "geojson"},
        timeout=(4, 18),
    )
    response.raise_for_status()
    payload = response.json()
    routes = payload.get("routes", []) if payload.get("code") == "Ok" else []
    if not routes:
        raise ValueError("The city routing service returned no road routes for these places.")

    alpha = min(max(float(alpha), 0.0), 1.0)
    is_ev = vehicle_type in {"EV", "Electric Car", "EV Scooter"}
    profile = VEHICLE_PROFILES.get(vehicle_type, {"cruise": 40.0})
    candidates = []
    for route in routes:
        distance_km = max(0.0, float(route["distance"]) / 1000.0)
        travel_time_min = max(0.0, float(route["duration"]) / 60.0)
        geometry = route.get("geometry", {}).get("coordinates", [])
        route_points = [[lat, lon] for lon, lat in geometry]
        travel_time_min *= _route_traffic_multiplier(route_points, traffic_multiplier, traffic_segments)
        if is_ev:
            fuel_ml = 0.0
            energy_kwh = distance_km * EV_KWH_PER_KM
            carbon_g = energy_kwh * INDIA_GRID_CO2_G_PER_KWH
            cost_inr = energy_kwh * EV_PRICE_INR_PER_KWH
        else:
            fuel_ml = distance_km * profile.get("cruise", 40.0)
            energy_kwh = 0.0
            carbon_g = fuel_ml * PETROL_CARBON_PER_ML
            cost_inr = (fuel_ml / 1000.0) * FUEL_PRICE_INR_PER_LITER
        stats = {
            "distance_km": distance_km,
            "travel_time_min": travel_time_min,
            "fuel_ml": fuel_ml,
            "energy_kwh": energy_kwh,
            "carbon_g": carbon_g,
            "cost_inr": cost_inr,
        }
        route_score = alpha * travel_time_min + (1 - alpha) * carbon_g / 10.0
        candidates.append((stats, route_score, route_points))

    fastest = min(candidates, key=lambda item: item[0]["travel_time_min"])
    eco = min(candidates, key=lambda item: item[1])
    standard_stats, _, standard_path = fastest
    eco_stats, _, eco_path = eco
    savings = {
        "carbon_g": standard_stats["carbon_g"] - eco_stats["carbon_g"],
        "fuel_ml": standard_stats["fuel_ml"] - eco_stats["fuel_ml"],
        "energy_kwh": standard_stats["energy_kwh"] - eco_stats["energy_kwh"],
        "money_inr": standard_stats["cost_inr"] - eco_stats["cost_inr"],
        "time_diff": eco_stats["travel_time_min"] - standard_stats["travel_time_min"],
    }
    savings["tree_equiv"] = savings["carbon_g"] / CO2_PER_DAY_TREE
    return {
        "standard_path": standard_path,
        "eco_path": eco_path,
        "standard": standard_stats,
        "eco": eco_stats,
        "savings": savings,
        "path_coordinates": True,
        "source": "City routing alternatives",
    }


def calculate_google_baseline(start_coords, end_coords, api_key, vehicle_type="ICE"):
    """Fetch Google's traffic-aware route and decode its overview geometry."""
    if not api_key or "redacted" in str(api_key).lower():
        raise ValueError("A valid Google Maps API key is not configured.")
    response = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.staticDuration,routes.polyline.encodedPolyline,routes.description,routes.travelAdvisory.speedReadingIntervals",
        },
        json={
            "origin": {"location": {"latLng": {"latitude": start_coords[0], "longitude": start_coords[1]}}},
            "destination": {"location": {"latLng": {"latitude": end_coords[0], "longitude": end_coords[1]}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "extraComputations": ["TRAFFIC_ON_POLYLINE"],
            "polylineQuality": "OVERVIEW",
            "polylineEncoding": "ENCODED_POLYLINE",
        },
        timeout=(4, 15),
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("routes"):
        message = payload.get("error", {}).get("message", "No route returned")
        raise ValueError(f"Google Routes could not return a route: {message}")

    route = payload["routes"][0]
    distance_km = float(route["distanceMeters"]) / 1000.0
    base_duration_s = float(str(route.get("staticDuration", route["duration"])).removesuffix("s"))
    live_duration_s = float(str(route["duration"]).removesuffix("s"))
    traffic_multiplier = min(max(live_duration_s / max(base_duration_s, 1.0), 1.0), 2.5)
    duration_s = live_duration_s
    duration_min = float(duration_s) / 60.0
    is_ev = vehicle_type in {"EV", "Electric Car", "EV Scooter"}
    if is_ev:
        fuel_ml = 0.0
        energy_kwh = distance_km * EV_KWH_PER_KM
        carbon_g = energy_kwh * INDIA_GRID_CO2_G_PER_KWH
        cost_inr = energy_kwh * EV_PRICE_INR_PER_KWH
    else:
        profile = VEHICLE_PROFILES.get(vehicle_type, {"cruise": 40.0})
        fuel_ml = distance_km * profile.get("cruise", 40.0)
        energy_kwh = 0.0
        carbon_g = fuel_ml * PETROL_CARBON_PER_ML
        cost_inr = fuel_ml / 1000.0 * FUEL_PRICE_INR_PER_LITER

    encoded = route["polyline"]["encodedPolyline"]
    lat = lon = 0
    coordinates = []
    index = 0
    while index < len(encoded):
        values = []
        for _ in range(2):
            result = shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            values.append(~(result >> 1) if result & 1 else result >> 1)
        lat += values[0]
        lon += values[1]
        coordinates.append([lat / 1e5, lon / 1e5])

    traffic_segments = []
    intervals = route.get("travelAdvisory", {}).get("speedReadingIntervals", [])
    for interval in intervals:
        first = int(interval.get("startPolylinePointIndex", 0))
        last = int(interval.get("endPolylinePointIndex", first))
        points = coordinates[first:min(last + 1, len(coordinates))]
        if points:
            traffic_segments.append({"speed": interval.get("speed", "NORMAL"), "points": points})

    return {
        "path": coordinates,
        "stats": {
            "distance_km": distance_km,
            "travel_time_min": duration_min,
            "fuel_ml": fuel_ml,
            "energy_kwh": energy_kwh,
            "carbon_g": carbon_g,
            "cost_inr": cost_inr,
        },
        "copyrights": "Google Maps",
        "summary": route.get("description", "Google Maps route"),
        "traffic_multiplier": traffic_multiplier,
        "has_live_traffic": "staticDuration" in route and "duration" in route,
        "traffic_segments": traffic_segments,
        "source": "Google Maps baseline",
    }

# --- ADVANCED VEHICLE PROFILES (EXPORTED) ---
VEHICLE_PROFILES = {
    "Economy Hatchback": {"cruise": 35.0, "idle": 10.0, "accel": 2.0},
    "Luxury SUV": {"cruise": 70.0, "idle": 20.0, "accel": 8.0},
    "EV Scooter": {"cruise": 0.0, "idle": 0.0, "accel": 0.0},
    "Electric Car": {"cruise": 0.0, "idle": 0.0, "accel": 0.0}
}

def calculate_environmental_weight(u, v, edge_data, vehicle_type="Economy Hatchback", alpha=0.3, traffic_multiplier=1.0):
    # NetworkX supplies a key-to-attributes mapping to callable weights on a
    # MultiGraph. Score each parallel road segment and use its least-cost edge.
    if edge_data and all(isinstance(value, dict) for value in edge_data.values()):
        return min(
            calculate_environmental_weight(u, v, data, vehicle_type, alpha, traffic_multiplier)
            for data in edge_data.values()
        )
    metrics = estimate_edge_metrics(edge_data, vehicle_type, traffic_multiplier)
    return alpha * metrics["travel_time_min"] + (1 - alpha) * metrics["carbon_g"] / 10.0

def calculate_savings(std_fuel_ml, eco_fuel_ml):
    # Preserve the sign: an eco-priority path can be slower or use more fuel.
    fuel_saved_ml = std_fuel_ml - eco_fuel_ml
    carbon_saved_g = fuel_saved_ml * PETROL_CARBON_PER_ML
    money_saved_inr = (fuel_saved_ml / 1000.0) * FUEL_PRICE_INR_PER_LITER
    pm25_saved = fuel_saved_ml * PM25_PER_ML_PETROL
    tree_equiv = carbon_saved_g / CO2_PER_DAY_TREE

    return {
        "fuel_ml": fuel_saved_ml,
        "carbon_g": carbon_saved_g,
        "money_inr": money_saved_inr,
        "pm25_g": pm25_saved,
        "tree_equiv": tree_equiv
    }

def load_network(path="bengaluru_grid.graphml"):
    """Load a graph path, resolving relative paths from this project directory."""
    graph_path = Path(path)
    if not graph_path.is_absolute():
        graph_path = Path(__file__).resolve().parent / graph_path
    if not graph_path.exists():
        raise FileNotFoundError(f"Graph file {graph_path} not found. Run fetch_map.py first.")
    return nx.read_graphml(graph_path)

def get_google_traffic_multiplier(start_coords, end_coords, api_key):
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": f"{start_coords[0]},{start_coords[1]}",
            "destinations": f"{end_coords[0]},{end_coords[1]}",
            "departure_time": "now",
            "traffic_model": "best_guess",
            "key": api_key
        }
        response = requests.get(url, params=params, timeout=(3.05, 6))
        data = response.json()
        if data.get('status') == 'OK':
            element = data['rows'][0]['elements'][0]
            if element.get('status') == 'OK':
                duration_val = element['duration']['value']
                duration_in_traffic_val = element.get('duration_in_traffic', {}).get('value', duration_val)
                return max(1.0, duration_in_traffic_val / duration_val)
    except Exception:
        pass
    return 1.0
