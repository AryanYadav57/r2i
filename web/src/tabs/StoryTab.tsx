import { ArrowRight, ChevronDown } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { MapViewState } from "@deck.gl/core";
import { ColumnLayer, PathLayer, ScatterplotLayer, TripsLayer } from "../lib/layers";
import CityMap from "../map/CityMap";
import {
  C, VEHICLE_HUES, fmt, hotNodes, positionAt, staticData, timestampsFor,
  type Avoided, type CompareResult, type FleetResult, type LonLat, type NodesData,
} from "../lib/data";
import { prefersReducedMotion, useClock } from "../lib/useClock";

const IDLE_G_PER_S = 0.462; // petrol car, 0.2 mL/s × 2310 g/L
type Cam = { longitude: number; latitude: number; zoom: number; pitch: number; bearing: number };

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = (t: number) => t * t * (3 - 2 * t);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerpAngle = (a: number, b: number, t: number) => a + ((((b - a) % 360) + 540) % 360 - 180) * t;
const mixCam = (a: Cam, b: Cam, t: number): Cam => ({
  longitude: lerp(a.longitude, b.longitude, t), latitude: lerp(a.latitude, b.latitude, t),
  zoom: lerp(a.zoom, b.zoom, t), pitch: lerp(a.pitch, b.pitch, t), bearing: lerpAngle(a.bearing, b.bearing, t),
});
/** amber → red for the worst junctions (t in 0..1). */
const heat = (t: number): number[] => [217 + (200 - 217) * t, 164 + (72 - 164) * t, 65 + (64 - 65) * t, 235];
const heading = (a: LonLat, b: LonLat) => (Math.atan2(b[0] - a[0], b[1] - a[1]) * 180) / Math.PI;

export default function StoryTab({ onNavigate, active = true }: { onNavigate: (tab: string) => void; active?: boolean }) {
  const [nodes, setNodes] = useState<NodesData | null>(null);
  const [race, setRace] = useState<CompareResult | null>(null);
  const [fleet, setFleet] = useState<FleetResult | null>(null);
  const [p, setP] = useState(0);                 // smoothed scroll position in steps (0..5)
  const scroller = useRef<HTMLDivElement>(null);
  const target = useRef(0);
  const still = prefersReducedMotion();

  useEffect(() => {
    staticData<NodesData>("nodes").then(setNodes).catch(() => {});
    staticData<CompareResult>("race").then(setRace).catch(() => {});
    staticData<FleetResult>("preset").then(setFleet).catch(() => {});
  }, []);

  // Damped follow of the scroll position. The loop runs only while catching up,
  // and keeps its own value so React re-renders never start a second loop.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = 0;
    let raf = 0, cur = 0, last = 0;
    const tick = (now: number) => {
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
      last = now;
      const k = still ? 1 : 1 - Math.exp(-dt * 9);          // frame-rate independent easing
      cur = lerp(cur, target.current, k);
      if (Math.abs(cur - target.current) < 0.0005) { cur = target.current; raf = 0; last = 0; }
      else raf = requestAnimationFrame(tick);
      setP(cur);
    };
    const onScroll = () => {
      target.current = el.scrollTop / el.clientHeight;
      if (!raf) raf = requestAnimationFrame(tick);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => { el.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, [still]);

  // Only the worst ~5% of junctions (top third of the shipped 15%), rescaled for colour/height.
  const cong = useMemo(() => {
    const ranked = [...hotNodes(nodes)].sort((x, y) => y[3] - x[3]);
    const top = ranked.slice(0, Math.max(1, Math.round(ranked.length / 10)));  // shipped file = top 15%, so this is ~1.5%
    return top.map((d, i) => [d[0], d[1], 1 - i / Math.max(1, top.length - 1), d[3]]);
  }, [nodes]);
  const hot = useMemo(() => (nodes ? nodes.nodes.reduce((a, b) => (b[2] > a[2] ? b : a)) : null), [nodes]);
  const raceT = useMemo(() => {
    if (!race) return null;
    const d = (m: CompareResult["r2i"]["metrics"]) => m.travel_time_s + m.total_idle_s;
    const b = { path: race.baseline.path, ts: timestampsFor(race.baseline.path, d(race.baseline.metrics)), c: C.base };
    const r = { path: race.r2i.path, ts: timestampsFor(race.r2i.path, d(race.r2i.metrics)), c: C.r2i };
    return { dur: Math.max(d(race.baseline.metrics), d(race.r2i.metrics)), b, r };
  }, [race]);

  const fleetT = useMemo(() => {
    if (!fleet?.r2i.vehicles.length) return null;
    const t0 = Math.min(...fleet.r2i.vehicles.map((v) => v.depart_s));
    return { t0, span: Math.max(...fleet.r2i.vehicles.map((v) => v.return_s)) - t0 };
  }, [fleet]);
  const raceProg = clamp((p - 2.6) / 1.0);       // scroll scrubs the race across steps 2.6 → 3.6
  const raceTime = raceT ? raceProg * raceT.dur : 0;
  const [idleT] = useClock(0, 60, 6, active && Math.abs(p - 1) < 0.9 && !still, true);

  // One camera keyframe per step: wide → dive to junction → lift & rotate → follow van → overview → orbit hub.
  const keys: Cam[] = useMemo(() => {
    const center: Cam = { longitude: 77.622, latitude: 12.935, zoom: 12.3, pitch: 30, bearing: -25 };
    const junction: Cam = hot ? { longitude: hot[0], latitude: hot[1], zoom: 16.6, pitch: 58, bearing: 30 } : center;
    const lifted: Cam = { longitude: 77.62, latitude: 12.935, zoom: 13.5, pitch: 60, bearing: -15 };
    let follow = lifted, overview = lifted;
    if (raceT) {
      const head = positionAt(raceT.r.path, raceT.r.ts, raceTime);
      const ahead = positionAt(raceT.r.path, raceT.r.ts, Math.min(raceT.dur, raceTime + 90));
      follow = { longitude: head[0], latitude: head[1], zoom: 15.2, pitch: 62, bearing: heading(head, ahead) };
      const mid = raceT.r.path[Math.floor(raceT.r.path.length / 2)];
      overview = { longitude: mid[0], latitude: mid[1], zoom: 13.4, pitch: 45, bearing: 0 };
    }
    const hub: Cam = fleet ? { longitude: fleet.scenario.hub.lon, latitude: fleet.scenario.hub.lat, zoom: 12.6, pitch: 48, bearing: 20 + clamp(p - 4.3, 0, 0.7) * 60 } : center;
    return [center, junction, lifted, follow, overview, hub];
  }, [hot, raceT, raceTime, fleet, p]);

  const i = Math.min(keys.length - 2, Math.floor(p));
  const view: MapViewState = mixCam(keys[i], keys[i + 1], ease(clamp(p - i)));
  const w = (k: number) => clamp(1 - Math.abs(p - k) * 1.4);   // how "present" step k is

  const layers = [
    new ColumnLayer({
      id: "cong", data: cong, diskResolution: 8, radius: 8, extruded: true,
      visible: p > 1.3 && p < 2.9, opacity: 0.85 * w(2),
      elevationScale: 0.12 + 0.88 * ease(clamp((p - 1.3) / 0.8)),
      getPosition: (d: number[]) => [d[0], d[1]], getElevation: (d: number[]) => (0.3 + d[2] ** 1.5) * 200,
      getFillColor: (d: number[]) => heat(d[2]),
    }),
    hot && new ScatterplotLayer({
      id: "puff", visible: w(1) > 0.01, opacity: w(1),
      data: [0, 1, 2, 3].map((k) => (idleT + k * 15) % 60), getPosition: () => [hot[0], hot[1]], radiusUnits: "meters",
      getRadius: (s: number) => 6 + s * 0.9, getFillColor: (s: number) => [180, 200, 190, Math.max(0, 170 - s * 2.8)],
      updateTriggers: { getRadius: idleT, getFillColor: idleT },
    }),
    race && new PathLayer({ id: "rb", data: [race.baseline.path], getPath: (q: LonLat[]) => q, widthMinPixels: 6, getColor: C.base, opacity: 0.25 + 0.45 * w(4), visible: p > 2.2 && p < 4.9 }),
    race && new PathLayer({ id: "rr", data: [race.r2i.path], getPath: (q: LonLat[]) => q, widthMinPixels: 4, getColor: C.r2i, opacity: 0.3 + 0.7 * w(4), visible: p > 2.2 && p < 4.9 }),
    raceT && new TripsLayer({
      id: "race", data: [raceT.b, raceT.r], currentTime: raceTime, trailLength: raceT.dur / 4, fadeTrail: true,
      visible: p > 2.4 && p < 4.2, getPath: (d: { path: LonLat[] }) => d.path, getTimestamps: (d: { ts: number[] }) => d.ts,
      getColor: (d: { c: number[] }) => d.c, widthMinPixels: 7, capRounded: true, jointRounded: true,
    }),
    raceT && new ScatterplotLayer({
      id: "heads", visible: p > 2.4 && p < 4.2, radiusMinPixels: 8, stroked: true, getLineColor: [255, 255, 255], lineWidthMinPixels: 2,
      data: [{ q: positionAt(raceT.b.path, raceT.b.ts, raceTime), c: C.base }, { q: positionAt(raceT.r.path, raceT.r.ts, raceTime), c: C.r2i }],
      getPosition: (d: { q: LonLat }) => d.q, getFillColor: (d: { c: number[] }) => d.c, updateTriggers: { getPosition: raceTime },
    }),
    race && new ScatterplotLayer({
      id: "av", data: race.avoided, visible: p > 2.8 && p < 4.9, opacity: Math.max(w(3), w(4)), getPosition: (a: Avoided) => [a.lon, a.lat],
      stroked: true, filled: false, getLineColor: [...C.amber, 230], lineWidthMinPixels: 2, radiusMinPixels: 6, getRadius: 28,
    }),
    fleet && fleetT && new TripsLayer({
      id: "fleet", data: fleet.r2i.vehicles, visible: p > 4.2, opacity: w(5),
      currentTime: fleetT.span * ease(clamp((p - 4.3) / 0.7)), trailLength: fleetT.span, fadeTrail: false,
      getPath: (v: { trajectory: number[][] }) => v.trajectory.map((q) => [q[0], q[1]]),
      getTimestamps: (v: { trajectory: number[][] }) => v.trajectory.map((q) => q[2] - fleetT.t0),
      getColor: (_: unknown, { index }: { index: number }) => VEHICLE_HUES[index % VEHICLE_HUES.length], widthMinPixels: 3,
      capRounded: true, jointRounded: true,
    }),
    fleet && new ScatterplotLayer({ id: "hub", data: [fleet.scenario.hub], visible: p > 4.2, opacity: w(5), getPosition: (h: { lat: number; lon: number }) => [h.lon, h.lat], radiusMinPixels: 10, getFillColor: [232, 240, 236], stroked: true, getLineColor: C.r2i, lineWidthMinPixels: 3 }),
  ].filter(Boolean);

  const rb = race?.baseline.metrics, rr = race?.r2i.metrics;
  const fb = fleet?.comparison.baseline, fr = fleet?.comparison.r2i;
  const steps = [
    <><div className="kicker">Route-to-Impact</div><h2>The shortest route isn't the cleanest one.</h2>
      <p>Navigation apps minimise kilometres or minutes. But in a dense city, a lot of fuel is burned standing still — waiting at junctions with the engine running.</p>
      <div className="scrollhint" aria-hidden="true"><ChevronDown size={18} />Scroll</div></>,
    <><div className="kicker">The hidden cost</div><h2>Every red light has a price.</h2>
      <p>A petrol car idling burns about 0.2 mL of fuel per second — <span className="mono">0.462 g</span> of CO₂ every second it waits.</p>
      <div className="bigstat">{(idleT * IDLE_G_PER_S).toFixed(1)} g</div>
      <p className="hint">CO₂ from one car waiting at this junction ({idleT.toFixed(0)} s).</p></>,
    <><div className="kicker">Making it visible</div><h2>Some junctions are far worse than others.</h2>
      <p>R2I scores every intersection from OpenStreetMap: how many streets meet, whether it is signalised, and how big the roads are. Taller, redder columns predict longer waits.</p>
      <p className="hint">No live traffic feed — a structural estimate anyone can reproduce.</p></>,
    <><div className="kicker">The race</div><h2>Same trip. Two routes.</h2>
      {rb && rr && <>
        <p><span style={{ color: "var(--base)" }}>Shortest</span> drives {fmt.km(rb.distance_km)}; <span style={{ color: "var(--r2i)" }}>R2I</span> drives {fmt.km(rr.distance_km)} but waits {fmt.min(rb.total_idle_s - rr.total_idle_s)} less.</p>
        <div className="stats">
          <div className="stat"><b style={{ color: "var(--base)" }}>{fmt.kg(rb.total_co2_g * raceProg)}</b><span>shortest CO₂</span></div>
          <div className="stat"><b className="good">{fmt.kg(rr.total_co2_g * raceProg)}</b><span>R2I CO₂</span></div>
          <div className="stat"><b>{Math.round(raceProg * 100)}%</b><span>of the trip</span></div>
        </div></>}</>,
    <><div className="kicker">Physics, not preference</div><h2>An electric van doesn't care about the queue.</h2>
      <p>Idling costs an EV almost nothing, so its best route is simply the fastest. A diesel van should avoid the worst junctions even if the drive is a little longer.</p>
      <p>That difference is exactly what a mixed delivery fleet can exploit.</p></>,
    <><div className="kicker">Scale it up</div><h2>Now plan a whole delivery fleet.</h2>
      {fb && fr && <p>{fleet!.scenario.orders.length} orders, {fleet!.scenario.vehicles.length} vehicles, one morning: {fmt.l(fb.fuel_ml)} → {fmt.l(fr.fuel_ml)} of fuel, {fmt.inr(fb.cost_inr)} → {fmt.inr(fr.cost_inr)}.</p>}
      <button className="btn primary" onClick={() => onNavigate("fleet")}>Open the fleet console<ArrowRight size={16} /></button></>,
  ];
  const goTo = (k: number) => scroller.current?.scrollTo({ top: k * (scroller.current?.clientHeight ?? 0), behavior: still ? "auto" : "smooth" });

  return (
    <div className="story" ref={scroller}>
      <div className="sticky"><CityMap layers={layers as never} viewState={view} interactive={false} buildings buildingsMinZoom={13} /></div>
      <div className="steps">
        {steps.map((s, k) => (
          <section key={k} className="step">
            <div className="card" style={{ opacity: ease(w(k)), transform: `translate3d(0, ${clamp(k - p, -1, 1) * 70}px, 0)` }}>{s}</div>
          </section>
        ))}
      </div>
      <nav className="storynav" aria-label="Story steps">
        <div className="bar"><i style={{ height: `${(p / (steps.length - 1)) * 100}%` }} /></div>
        {steps.map((_, k) => <button key={k} aria-label={`Go to step ${k + 1}`} aria-current={Math.round(p) === k ? "step" : undefined} onClick={() => goTo(k)} />)}
      </nav>
    </div>
  );
}
