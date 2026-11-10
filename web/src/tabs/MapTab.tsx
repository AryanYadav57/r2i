import { ArrowUpDown, ChartLine, MapPin, Play, Search, TriangleAlert, Waves } from "lucide-react";
import { CompareTable, ListRow, Panel, Section, Stat, StatRow, Toggle } from "../ui";
import { useEffect, useMemo, useState } from "react";
import { ColumnLayer, ScatterplotLayer, TextLayer, TripsLayer, casedPath } from "../lib/layers";
import type { PickingInfo } from "@deck.gl/core";
import CityMap, { type FlyTarget } from "../map/CityMap";
import {
  C, api, apiAvailable, congestionColor, fmt, hotNodes, positionAt, staticData, timestampsFor,
  type Avoided, type CompareResult, type LonLat, type NodesData,
} from "../lib/data";
import { useClock } from "../lib/useClock";

const VEHICLES = [
  ["ICE", "Petrol car"], ["EV", "Electric car"], ["van_diesel", "Diesel mini-truck"],
  ["2w_petrol", "Petrol 2-wheeler"], ["van_ev", "Electric mini-truck"],
] as const;

interface SweepPoint { alpha: number; time_s: number; co2_g: number }

export default function MapTab({ active = true }: { active?: boolean }) {
  const [live, setLive] = useState(false);
  const [nodes, setNodes] = useState<NodesData | null>(null);
  const [res, setRes] = useState<CompareResult | null>(null);
  const [origin, setOrigin] = useState<LonLat | null>(null);
  const [dest, setDest] = useState<LonLat | null>(null);
  const [vehicle, setVehicle] = useState("van_diesel");
  const [alpha, setAlpha] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showCong, setShowCong] = useState(false);
  const [allJunctions, setAllJunctions] = useState(false);
  const [showAvoided, setShowAvoided] = useState(true);
  const [moreJunctions, setMoreJunctions] = useState(false);
  const [racing, setRacing] = useState(false);
  const [wave, setWave] = useState<{ visited: [number, number, number][]; path: LonLat[] } | null>(null);
  const [sweep, setSweep] = useState<SweepPoint[] | null>(null);
  const [fly, setFly] = useState<FlyTarget | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ label: string; lat: number; lon: number }[]>([]);

  useEffect(() => {
    apiAvailable().then(setLive);
    staticData<NodesData>("nodes").then(setNodes).catch(() => {});
    staticData<CompareResult>("race").then((r) => {
      setRes(r);
      if (r.request) {
        setOrigin([r.request.origin.lon, r.request.origin.lat]);
        setDest([r.request.dest.lon, r.request.dest.lat]);
        setVehicle(r.request.vehicle);
      }
    }).catch(() => {});
  }, []);

  async function run(o = origin, d = dest, v = vehicle, a = alpha) {
    if (!o || !d || !live) return;
    setBusy(true); setErr(null); setWave(null); setSweep(null);
    try {
      const body = { origin: { lon: o[0], lat: o[1] }, dest: { lon: d[0], lat: d[1] }, vehicle: v, alpha: a };
      setRes(await api<CompareResult>("/route/compare", body));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  function onClick(info: PickingInfo) {
    if (!info.coordinate || !live) return;
    const p = info.coordinate.slice(0, 2) as LonLat;
    if (!origin || dest) { setOrigin(p); setDest(null); setRes(null); }
    else { setDest(p); run(origin, p); }
  }

  async function search() {
    if (!query.trim() || !live) return;
    try { setHits(await api(`/geocode?q=${encodeURIComponent(query)}`)); } catch { setHits([]); }
  }

  async function explore() {
    if (!origin || !dest || !live) return;
    const body = { origin: { lon: origin[0], lat: origin[1] }, dest: { lon: dest[0], lat: dest[1] }, objective: vehicle === "ICE" ? "car_petrol" : vehicle === "EV" ? "car_ev" : vehicle };
    setWave(await api("/route/explore", body));
  }

  async function runSweep() {
    if (!origin || !dest || !live) return;
    const body = { origin: { lon: origin[0], lat: origin[1] }, dest: { lon: dest[0], lat: dest[1] }, vehicle, alphas: [0, 0.25, 0.5, 1, 2, 4, 8, 16] };
    setSweep((await api<{ points: SweepPoint[] }>("/route/sweep", body)).points);
  }

  // ---------------- race timing (proportional along each path, real total durations)
  const race = useMemo(() => {
    if (!res) return null;
    const dur = (m: CompareResult["r2i"]["metrics"]) => m.travel_time_s + m.total_idle_s;
    return {
      b: { path: res.baseline.path, ts: timestampsFor(res.baseline.path, dur(res.baseline.metrics)), dur: dur(res.baseline.metrics) },
      r: { path: res.r2i.path, ts: timestampsFor(res.r2i.path, dur(res.r2i.metrics)), dur: dur(res.r2i.metrics) },
    };
  }, [res]);
  const raceEnd = race ? Math.max(race.b.dur, race.r.dur) + 20 : 1;
  const [t, setT] = useClock(0, raceEnd, raceEnd / 14, racing && active);
  useEffect(() => { if (racing && t >= raceEnd) setRacing(false); }, [t, raceEnd, racing]);

  const [waveT] = useClock(0, wave?.visited.length ?? 1, (wave?.visited.length ?? 1) / 5, !!wave && active);

  // Default: only the worst ~5% junctions (slim amber→red); "All junctions" shows the full shipped set.
  const congNodes = useMemo(() => {
    const all = hotNodes(nodes);
    if (allJunctions) return all.map((d) => [...d, 0]);
    const ranked = [...all].sort((x, y) => y[3] - x[3]);
    const top = ranked.slice(0, Math.max(1, Math.round(ranked.length / 3)));
    return top.map((d, i) => [d[0], d[1], 1 - i / Math.max(1, top.length - 1), d[3], 1]);
  }, [nodes, allJunctions]);
  const heat = (t: number) => [217 + (200 - 217) * t, 164 + (72 - 164) * t, 65, 235];

  const pins = [origin && { p: origin, l: "A" }, dest && { p: dest, l: "B" }].filter(Boolean) as { p: LonLat; l: string }[];
  const layers = [
    showCong && new ColumnLayer({
      id: "congestion", data: congNodes, diskResolution: 8, radius: allJunctions ? 12 : 8, extruded: true, pickable: true,
      getPosition: (d: number[]) => [d[0], d[1]], getElevation: (d: number[]) => (0.2 + d[2] ** 1.5) * 380,
      getFillColor: (d: number[]) => (d[4] ? heat(d[2]) : congestionColor(d[2])), opacity: 0.7,
      updateTriggers: { getFillColor: allJunctions },
    }),
    wave && new ScatterplotLayer({
      id: "wave", data: wave.visited, radiusMinPixels: 2, getRadius: 10,
      getPosition: (d: number[]) => [d[0], d[1]],
      getFillColor: (_: unknown, { index }: { index: number }) => (index < waveT ? [111, 168, 201, 160] : [0, 0, 0, 0]),
      updateTriggers: { getFillColor: Math.floor(waveT / 20) },
    }),
    ...(res ? casedPath({ id: "base", data: [res.baseline.path], getPath: (p: LonLat[]) => p, widthMinPixels: 4, getColor: [...C.base, racing ? 90 : 230] }) : []),
    ...(res ? casedPath({ id: "r2i", data: [res.r2i.path], getPath: (p: LonLat[]) => p, widthMinPixels: 5, getColor: [...C.r2i, racing ? 90 : 255] }) : []),
    res && showAvoided && new ScatterplotLayer({
      id: "avoided", data: res.avoided, pickable: true, radiusMinPixels: 4, getRadius: 12, getPosition: (a: Avoided) => [a.lon, a.lat],
      getFillColor: [...C.amber, 240], stroked: true, getLineColor: [...C.casing, 255], lineWidthMinPixels: 1.5,
    }),
    race && racing && new TripsLayer({
      id: "trips", data: [{ ...race.b, c: C.base }, { ...race.r, c: C.r2i }], currentTime: t, trailLength: raceEnd / 5,
      getPath: (d: { path: LonLat[] }) => d.path, getTimestamps: (d: { ts: number[] }) => d.ts,
      getColor: (d: { c: number[] }) => d.c, widthMinPixels: 6, capRounded: true, jointRounded: true, fadeTrail: true,
    }),
    race && racing && new ScatterplotLayer({
      id: "heads", data: [{ p: positionAt(race.b.path, race.b.ts, t), c: C.base }, { p: positionAt(race.r.path, race.r.ts, t), c: C.r2i }],
      getPosition: (d: { p: LonLat }) => d.p, getFillColor: (d: { c: number[] }) => d.c, radiusMinPixels: 7, stroked: true,
      getLineColor: [...C.casing, 255], lineWidthMinPixels: 2, updateTriggers: { getPosition: t },
    }),
    new ScatterplotLayer({
      id: "od", data: pins, getPosition: (d: { p: LonLat }) => d.p, radiusMinPixels: 11, radiusMaxPixels: 11,
      getFillColor: [232, 240, 236], stroked: true, getLineColor: [...C.casing, 255], lineWidthMinPixels: 2,
    }),
    new TextLayer({
      id: "od-label", data: pins, getPosition: (d: { p: LonLat }) => d.p, getText: (d: { l: string }) => d.l,
      getSize: 12, getColor: [...C.casing, 255], fontFamily: "Geist, sans-serif", fontWeight: 700,
      getTextAnchor: "middle", getAlignmentBaseline: "center",
    }),
  ].filter(Boolean);

  // Frame each new route: centre on its midpoint, zoom from its extent.
  useEffect(() => {
    if (!res?.r2i.path.length) return;
    const pts = [...res.r2i.path, ...res.baseline.path];
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    setFly({ longitude: (Math.min(...xs) + Math.max(...xs)) / 2, latitude: (Math.min(...ys) + Math.max(...ys)) / 2,
      zoom: Math.max(11.5, Math.min(15, Math.log2(0.9 / Math.max(span, 1e-4)) + 8.6)), pitch: 35 });
  }, [res]);
  const m = res && { b: res.baseline.metrics, r: res.r2i.metrics };
  const frac = (dur: number) => (racing ? Math.min(1, t / dur) : 1);
  const swap = () => { if (origin && dest) { setOrigin(dest); setDest(origin); run(dest, origin); } };
  const short = (p: LonLat | null) => (p ? `${p[1].toFixed(4)}, ${p[0].toFixed(4)}` : "Click the map");

  return (
    <div className="mapwrap">
      <CityMap layers={layers as never} onClick={onClick} flyTo={fly}
        getTooltip={(i) => (i.layer?.id === "congestion" ? `Congestion score ${(i.object as number[])[3].toFixed(2)}` : i.layer?.id === "avoided" ? `Avoided junction · ~${(i.object as { idle_s: number }).idle_s.toFixed(0)} s idle` : null)} />

      <Panel className="left" title="Single trip" subtitle={live ? "Click the map for A, then B, or search a place." : "Precomputed trip. Start the API to route anywhere."}>
        <Section title="Route">
          {live && (
            <div className="ui-search"><Search size={14} /><input type="text" placeholder="Search a place in Bengaluru" value={query}
              onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} aria-label="Search place" /></div>
          )}
          {hits.length > 0 && (
            <div className="ui-hits">{hits.map((h) => (
              <ListRow key={h.label} icon={<MapPin size={14} />} title={h.label.split(",").slice(0, 2).join(",")} onClick={() => {
                const p: LonLat = [h.lon, h.lat];
                if (!origin || dest) { setOrigin(p); setDest(null); } else { setDest(p); run(origin, p); }
                setFly({ longitude: h.lon, latitude: h.lat, zoom: 14 }); setHits([]);
              }} />))}</div>
          )}
          <div className="ui-ab">
            <div><span className="ui-pin">A</span><span className="mono">{short(origin)}</span></div>
            <div><span className="ui-pin">B</span><span className="mono">{short(dest)}</span></div>
            <button className="ui-icon-btn" aria-label="Swap start and end" disabled={!live || !origin || !dest} onClick={swap}><ArrowUpDown size={14} /></button>
          </div>
        </Section>
        <Section title="Vehicle">
          <select id="veh" value={vehicle} disabled={!live} aria-label="Vehicle" onChange={(e) => { setVehicle(e.target.value); run(origin, dest, e.target.value); }}>
            {VEHICLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Section>
        <Section title="Preference" action={<span className="mono ui-dim">α {alpha}</span>}>
          <input id="alpha" type="range" min={0} max={8} step={0.25} value={alpha} disabled={!live} aria-label="Cleaner to faster preference"
            style={{ "--pct": `${(alpha / 8) * 100}%` } as React.CSSProperties}
            onChange={(e) => setAlpha(+e.target.value)} onMouseUp={() => run()} onTouchEnd={() => run()} onKeyUp={() => run()} />
          <div className="ui-scale"><span>Cleaner</span><span>Faster</span></div>
        </Section>
        <Section title="Layers">
          <Toggle label="Congestion hotspots" hint="Worst 5% of junctions" checked={showCong} onChange={setShowCong} />
          {showCong && <Toggle label="All junctions" checked={allJunctions} onChange={setAllJunctions} />}
          <Toggle label="Avoided junctions" checked={showAvoided} onChange={setShowAvoided} />
        </Section>
        <Section title="Animate">
          <div className="ui-actions">
            <button className="btn primary" disabled={!res} onClick={() => { setT(0); setRacing(true); }}><Play size={14} />Race</button>
            <button className="btn" disabled={!live || !dest} onClick={explore}><Waves size={14} />Search wave</button>
            <button className="btn" disabled={!live || !dest} onClick={runSweep}><ChartLine size={14} />Trade-off</button>
          </div>
        </Section>
        {busy && <p className="hint">Routing…</p>}
        {err && <p className="hint bad">{err}</p>}
        <div className="ui-legend">
          <span><i style={{ background: "var(--data-r2i)" }} />R2I route</span>
          <span><i style={{ background: "var(--data-base)" }} />Shortest</span>
          <span><i className="dot" style={{ background: "var(--data-amber)" }} />Avoided</span>
        </div>
      </Panel>

      {m && race && (
        <Panel className="right" title={res!.diverged ? "Same trip, different road" : "Routes agree"}>
          <StatRow>
            <Stat label="Tailpipe CO₂" value={fmt.pct(m.r.total_co2_g, m.b.total_co2_g)} tone={m.r.total_co2_g < m.b.total_co2_g ? "good" : undefined} />
            <Stat label="Less idling" value={fmt.min(m.b.total_idle_s - m.r.total_idle_s)} />
            <Stat label="Saved" value={fmt.inr(m.b.cost_inr - m.r.cost_inr)} />
          </StatRow>
          <CompareTable head={["Shortest", "R2I"]} rows={[
            { label: "Distance", a: m.b.distance_km * frac(race.b.dur), b: m.r.distance_km * frac(race.r.dur), format: fmt.km },
            { label: "Time incl. idling", a: (m.b.travel_time_s + m.b.total_idle_s) * frac(race.b.dur), b: (m.r.travel_time_s + m.r.total_idle_s) * frac(race.r.dur), format: fmt.min },
            { label: "Idling", a: m.b.total_idle_s * frac(race.b.dur), b: m.r.total_idle_s * frac(race.r.dur), format: fmt.min },
            { label: "Tailpipe CO₂", a: m.b.total_co2_g * frac(race.b.dur), b: m.r.total_co2_g * frac(race.r.dur), format: fmt.kg },
            { label: "Fuel", a: m.b.fuel_ml * frac(race.b.dur), b: m.r.fuel_ml * frac(race.r.dur), format: fmt.l },
            { label: "Energy cost", a: m.b.cost_inr * frac(race.b.dur), b: m.r.cost_inr * frac(race.r.dur), format: fmt.inr },
          ]} />
          {res!.avoided.length > 0 && (
            <Section title="Junctions it avoids">
              {res!.avoided.slice(0, moreJunctions ? 8 : 3).map((a, i) => (
                <ListRow key={i} icon={<TriangleAlert size={13} />} title={<span className="ui-sev"><i style={{ width: `${Math.min(100, a.congestion * 160)}%` }} /></span>}
                  trailing={`~${a.idle_s.toFixed(0)} s`} onClick={() => setFly({ longitude: a.lon, latitude: a.lat, zoom: 16.5, pitch: 35 })} />
              ))}
              {res!.avoided.length > 3 && <button className="ui-link" onClick={() => setMoreJunctions(!moreJunctions)}>{moreJunctions ? "Show less" : `Show ${Math.min(8, res!.avoided.length) - 3} more`}</button>}
            </Section>
          )}
          {sweep && <Section title="Trade-off across α"><SweepChart points={sweep} alpha={alpha} /></Section>}
        </Panel>
      )}
    </div>
  );
}

function SweepChart({ points, alpha }: { points: SweepPoint[]; alpha: number }) {
  const W = 290, H = 150, P = 30;
  const xs = points.map((p) => p.time_s / 60), ys = points.map((p) => p.co2_g);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v: number) => P + ((v - x0) / (x1 - x0 || 1)) * (W - P - 8);
  const sy = (v: number) => H - P + 8 - ((v - y0) / (y1 - y0 || 1)) * (H - P - 8);
  const near = points.reduce((a, b) => (Math.abs(b.alpha - alpha) < Math.abs(a.alpha - alpha) ? b : a));
  return (
    <>
            <svg width={W} height={H} role="img" aria-label="Travel time versus CO2 for different alpha values">
        <polyline fill="none" stroke="var(--muted)" strokeWidth={1.5} points={points.map((p) => `${sx(p.time_s / 60)},${sy(p.co2_g)}`).join(" ")} />
        {points.map((p) => <circle key={p.alpha} cx={sx(p.time_s / 60)} cy={sy(p.co2_g)} r={p === near ? 6 : 3.5} fill={p === near ? "var(--data-r2i)" : "var(--faint)"}><title>{`α=${p.alpha}: ${fmt.min(p.time_s)}, ${fmt.kg(p.co2_g)}`}</title></circle>)}
        <text x={P} y={H - 4} fill="var(--faint)" fontSize={10}>time (min) →</text>
        <text x={2} y={12} fill="var(--faint)" fontSize={10}>CO₂ ↑</text>
      </svg>
    </>
  );
}
