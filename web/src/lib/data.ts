// Types, data loading and formatting shared across tabs.

export type LonLat = [number, number];

export interface RouteMetrics {
  distance_km: number; travel_time_s: number; total_idle_s: number; total_co2_g: number;
  fuel_ml: number; energy_kwh: number; grid_co2_g: number; cost_inr: number; node_count: number;
}
export interface Avoided { lon: number; lat: number; congestion: number; idle_s: number }
export interface CompareResult {
  baseline: { path: LonLat[]; metrics: RouteMetrics };
  r2i: { path: LonLat[]; metrics: RouteMetrics };
  delta: Record<string, number>; diverged: boolean; avoided: Avoided[];
  request?: { origin: { lat: number; lon: number }; dest: { lat: number; lon: number }; vehicle: string };
}
export interface NodesData { count: number; nodes: [number, number, number, number][] }

export interface Stop {
  order_id: string; lat: number; lon: number; weight_kg: number; arrive_s: number; start_s: number;
  depart_s: number; tw_start_s: number; tw_end_s: number; load_after_kg: number; late_s: number;
}
export interface FleetEvent {
  t: number; type: "depart" | "idle" | "deliver" | "return"; lat: number; lon: number;
  seconds?: number; co2_g?: number; order_id?: string; load_kg?: number; late?: boolean;
}
export interface VehiclePlan {
  id: string; spec_key: string; label: string; fuel: string; capacity_kg: number; start_load_kg: number;
  depart_s: number; return_s: number; stops: Stop[]; trajectory: [number, number, number][];
  events: FleetEvent[]; objective_before_reorder: number; objective_after_reorder: number;
  metrics: Record<string, number>;
}
export interface Plan { vehicle_ids: string[]; vehicles: VehiclePlan[]; unserved: string[]; totals: Record<string, number> }
export interface Insight { kind: string; title: string; detail: string; lat?: number; lon?: number; vehicle_id?: string }
export interface FleetResult {
  scenario: {
    name: string; hub: { lat: number; lon: number };
    orders: { id: string; lat: number; lon: number; weight_kg: number; tw_start_s: number; tw_end_s: number }[];
    vehicles: { id: string; spec_key: string; label: string; fuel: string; capacity_kg: number }[];
  };
  baseline: Plan; r2i: Plan; insights: Insight[];
  comparison: { baseline: Record<string, number>; r2i: Record<string, number>; delta: Record<string, number> };
}

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(API + path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

const cache = new Map<string, Promise<unknown>>();
/** Undo scripts/slim_preset.py: integer deltas (1e-5 deg, 0.1 s) -> [lon, lat, t] per vehicle. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function decodeFleet(d: any) {
  for (const plan of [d.baseline, d.r2i]) {
    for (const v of plan.vehicles) {
      const out: [number, number, number][] = [];
      let x = 0, y = 0, t = 0;
      for (let i = 0; i < v.traj.length; i += 3) {
        x += v.traj[i]; y += v.traj[i + 1]; t += v.traj[i + 2];
        out.push([x / 1e5, y / 1e5, t / 10]);
      }
      v.trajectory = out;
      delete v.traj;
    }
  }
  return d;
}

/** Precomputed JSON, fetched and parsed once per page load. */
export function staticData<T>(name: string): Promise<T> {
  if (!cache.has(name)) {
    cache.set(name, fetch(`${import.meta.env.BASE_URL}scenarios/${name}.json`).then((res) => {
      if (!res.ok) throw new Error(`missing ${name}.json`);
      return res.json().then((d) => (d?.encoding === "traj-delta-v1" ? decodeFleet(d) : d));
    }));
  }
  return cache.get(name) as Promise<T>;
}

let apiUp: Promise<boolean> | null = null;
export function apiAvailable(): Promise<boolean> {
  apiUp ??= fetch(API + "/health").then((r) => r.ok).catch(() => false);
  return apiUp;
}

// ---------------------------------------------------------------- formatting
export const fmt = {
  km: (v: number) => `${v.toFixed(v < 10 ? 2 : 1)} km`,
  min: (s: number) => `${(s / 60).toFixed(1)} min`,
  kg: (g: number) => (Math.abs(g) >= 1000 ? `${(g / 1000).toFixed(2)} kg` : `${g.toFixed(0)} g`),
  inr: (v: number) => `₹${v.toFixed(v < 100 ? 1 : 0)}`,
  l: (ml: number) => `${(ml / 1000).toFixed(2)} L`,
  kwh: (v: number) => `${v.toFixed(2)} kWh`,
  clock: (s: number) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  },
  pct: (a: number, b: number) => (b ? `${(((a - b) / b) * 100).toFixed(1)}%` : "—"),
};

// ------------------------------------------------------------------- colours
export const C = {
  r2i: [79, 163, 107] as [number, number, number],       // muted leaf (data)
  base: [196, 106, 126] as [number, number, number],     // muted rose (data)
  amber: [217, 164, 65] as [number, number, number],
  casing: [11, 18, 16] as [number, number, number],
  ink: [226, 232, 240] as [number, number, number],
};

/** Distinct vehicle hues (colour-blind friendly-ish, paired with dash/opacity for baseline). */
export const VEHICLE_HUES: [number, number, number][] = [
  [111, 168, 201], [111, 191, 154], [201, 180, 111], [156, 143, 201],
  [201, 143, 111], [196, 127, 158], [111, 181, 176], [150, 180, 120],
];

export function congestionColor(s: number): [number, number, number, number] {
  // green -> amber -> red
  const t = Math.min(1, Math.max(0, s));  // s already normalised to [0, 1]
  const r = Math.round(52 + (239 - 52) * t), g = Math.round(211 - (211 - 68) * t), b = Math.round(153 - (153 - 68) * t);
  return [r, g, b, 200];
}

/** Assign timestamps along a path proportional to distance, spanning totalS seconds. */
export function timestampsFor(path: LonLat[], totalS: number): number[] {
  const seg = path.slice(1).map((p, i) => Math.hypot(p[0] - path[i][0], p[1] - path[i][1]));
  const total = seg.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  return [0, ...seg.map((d) => (acc += (d / total) * totalS))];
}

/** Position along timestamped path at time t. */
export function positionAt(path: LonLat[], ts: number[], t: number): LonLat {
  if (t <= ts[0]) return path[0];
  for (let i = 1; i < ts.length; i++) {
    if (t <= ts[i]) {
      const f = (t - ts[i - 1]) / (ts[i] - ts[i - 1] || 1);
      return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * f, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * f];
    }
  }
  return path[path.length - 1];
}

/**
 * Keep the most congested `keep` share of junctions and rescale their scores to
 * [0, 1] within that band (raw scores cluster tightly, so absolute colouring is flat).
 * Returns [lon, lat, t, rawScore].
 */
export function hotNodes(data: NodesData | null, keep = 1): [number, number, number, number][] {
  if (!data) return [];
  const scores = data.nodes.map((n) => n[2]).sort((a, b) => a - b);
  const lo = scores[Math.floor((1 - keep) * (scores.length - 1))], hi = scores[scores.length - 1];
  return data.nodes.filter((n) => n[2] >= lo).map((n) => [n[0], n[1], (n[2] - lo) / (hi - lo || 1), n[2]]);
}
