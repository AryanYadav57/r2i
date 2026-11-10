import { ArrowUp, Map as MapIcon } from "lucide-react";
import { Stat, StatRow } from "../ui";
import { useEffect, useRef, useState } from "react";
import { PathLayer, ScatterplotLayer } from "../lib/layers";
import CityMap, { type FlyTarget } from "../map/CityMap";
import { C, api, apiAvailable, fmt, type Avoided, type LonLat, type RouteMetrics } from "../lib/data";

interface RouteArtifact {
  type: "route"; vehicle: string; origin: LonLat; dest: LonLat; avoided: Avoided[];
  baseline: { path: LonLat[]; metrics: RouteMetrics }; r2i: { path: LonLat[]; metrics: RouteMetrics };
}
interface Turn { role: "user" | "assistant"; content: string; artifacts?: RouteArtifact[]; error?: boolean }

const SUGGESTIONS = [
  "Compare a diesel van from Forum Mall to Indiranagar 100 Feet Road",
  "How much does the demo fleet save in a year?",
  "Should an EV take a different route than a petrol car?",
  "Why are some junctions worse than others?",
];

function mid(path: LonLat[]): FlyTarget {
  const [lon, lat] = path[Math.floor(path.length / 2)];
  return { longitude: lon, latitude: lat, zoom: 13.6, pitch: 45 };
}

export default function AskTab() {
  const [live, setLive] = useState<boolean | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [route, setRoute] = useState<RouteArtifact | null>(null);
  const [fly, setFly] = useState<FlyTarget | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { apiAvailable().then(setLive); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history: Turn[] = [...turns.filter((t) => !t.error), { role: "user", content: q }];
    setTurns([...turns, { role: "user", content: q }]);
    setDraft(""); setBusy(true);
    try {
      const res = await api<{ answer: string; artifacts: RouteArtifact[] }>("/ask", {
        messages: history.map(({ role, content }) => ({ role, content })),
      });
      setTurns((t) => [...t, { role: "assistant", content: res.answer, artifacts: res.artifacts }]);
      const last = res.artifacts.filter((a) => a.type === "route").pop();
      if (last) { setRoute(last); setFly(mid(last.r2i.path)); }
    } catch (e) {
      const msg = String(e).includes("503") ? "Ask AI isn't configured on this server yet. Set ANTHROPIC_API_KEY and restart the API."
        : `Something went wrong: ${String(e).slice(0, 160)}`;
      setTurns((t) => [...t, { role: "assistant", content: msg, error: true }]);
    } finally { setBusy(false); }
  }

  const layers = route ? [
    new PathLayer({ id: "ab", data: [route.baseline.path], getPath: (p: LonLat[]) => p, widthMinPixels: 7, getColor: [...C.base, 170], capRounded: true, jointRounded: true }),
    new PathLayer({ id: "ar", data: [route.r2i.path], getPath: (p: LonLat[]) => p, widthMinPixels: 4, getColor: [...C.r2i, 255], capRounded: true, jointRounded: true }),
    new ScatterplotLayer({ id: "aav", data: route.avoided, getPosition: (a: Avoided) => [a.lon, a.lat], stroked: true, filled: false, getLineColor: [...C.amber, 230], lineWidthMinPixels: 2, radiusMinPixels: 6, getRadius: 28 }),
    new ScatterplotLayer({ id: "aod", data: [route.origin, route.dest], getPosition: (p: LonLat) => p, radiusMinPixels: 7, getFillColor: [255, 255, 255], stroked: true, getLineColor: [11, 116, 67], lineWidthMinPixels: 3 }),
  ] : [];

  const empty = turns.length === 0;
  return (
    <div className="mapwrap">
      <CityMap layers={layers as never} flyTo={fly} />
      <div className="ask-bg" aria-hidden="true" />
      <div className="ask">
        {empty && (
          <div className="hero">
            <h1>Ask anything about<br />your routes.</h1>
            <p>Compare trips, explain junctions, or size up the fleet. Answers come straight from the R2I engine.</p>
          </div>
        )}
        {!empty && (
          <div className="thread" aria-live="polite">
            {turns.map((t, i) => (
              <div key={i} className={`bubble ${t.role === "user" ? "user" : "ai"}`}>
                {t.content}
                {t.artifacts?.filter((a) => a.type === "route").map((a, j) => <RouteChips key={j} a={a} onShow={() => { setRoute(a); setFly(mid(a.r2i.path)); }} />)}
              </div>
            ))}
            {busy && <div className="bubble ai typing">Thinking with the routing engine…</div>}
            <div ref={end} />
          </div>
        )}
        <form className="askbar" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={live === false}
            placeholder={live === false ? "Start the API to use Ask AI" : "Ask about a trip, a junction or the fleet…"} aria-label="Ask a question" />
          <button type="submit" disabled={busy || !draft.trim() || live === false} aria-label="Send"><ArrowUp size={18} /></button>
        </form>
        {empty && (
          <div className="chips">
            {SUGGESTIONS.map((s) => <button key={s} className="chip" disabled={live === false} onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
      </div>
    </div>
  );
}

function RouteChips({ a, onShow }: { a: RouteArtifact; onShow: () => void }) {
  const b = a.baseline.metrics, r = a.r2i.metrics;
  const time = (m: RouteMetrics) => m.travel_time_s + m.total_idle_s;
  const co2 = b.total_co2_g ? ((r.total_co2_g - b.total_co2_g) / b.total_co2_g) * 100 : 0;
  return (
    <div>
      <StatRow>
        <Stat label="Tailpipe CO₂" value={b.total_co2_g ? `${co2.toFixed(0)}%` : "0 g"} tone={co2 < 0 ? "good" : undefined} />
        <Stat label="Less idling" value={fmt.min(b.total_idle_s - r.total_idle_s)} />
        <Stat label="Trip time" value={(time(r) - time(b) >= 0 ? "+" : "") + fmt.min(time(r) - time(b))} />
      </StatRow>
      <button className="btn" onClick={onShow}><MapIcon size={14} />Show on map</button>
    </div>
  );
}
