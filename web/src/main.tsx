import { BookOpen, Circle, FileText, Map as MapIcon, Route, Sparkles, Truck } from "lucide-react";
import { Component, StrictMode, Suspense, lazy, useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
// Tabs load on demand; once visited they stay mounted (hidden) so the map is never rebuilt.
const StoryTab = lazy(() => import("./tabs/StoryTab"));
const MapTab = lazy(() => import("./tabs/MapTab"));
const FleetTab = lazy(() => import("./tabs/FleetTab"));
const AskTab = lazy(() => import("./tabs/AskTab"));
const MethodTab = lazy(() => import("./tabs/MethodTab"));
import { apiAvailable } from "./lib/data";

/** Keeps one tab's failure (e.g. a map error) from blanking the whole app. */
class TabBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <div className="stage loading"><div>This view hit an error. <button className="btn" onClick={() => this.setState({ failed: false })}>Retry</button></div></div>
      : this.props.children;
  }
}

const TABS = [
  { id: "story", label: "Story", icon: BookOpen, el: StoryTab },
  { id: "map", label: "Map", icon: MapIcon, el: MapTab },
  { id: "fleet", label: "Fleet", icon: Truck, el: FleetTab },
  { id: "ask", label: "Ask AI", icon: Sparkles, el: AskTab },
  { id: "method", label: "Method", icon: FileText, el: MethodTab },
] as const;
type TabId = (typeof TABS)[number]["id"];

function App() {
  const initial = (location.hash.slice(1) as TabId) || "story";
  const [tab, setTab] = useState<TabId>(TABS.some((t) => t.id === initial) ? initial : "story");
  const [live, setLive] = useState<boolean | null>(null);

  useEffect(() => { apiAvailable().then(setLive); }, []);
  useEffect(() => {
    const onHash = () => { const h = location.hash.slice(1) as TabId; if (TABS.some((t) => t.id === h)) setTab(h); };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("popstate", onHash);
    return () => { window.removeEventListener("hashchange", onHash); window.removeEventListener("popstate", onHash); };
  }, []);
  const [visited, setVisited] = useState<TabId[]>([tab]);
  const go = (id: TabId) => {
    setTab(id); history.replaceState(null, "", `#${id}`);
    setVisited((v) => (v.includes(id) ? v : [...v, id]));
  };
  useEffect(() => { setVisited((v) => (v.includes(tab) ? v : [...v, tab])); }, [tab]);
  useEffect(() => {
    const idle = (cb: () => void) => ("requestIdleCallback" in window ? (window as any).requestIdleCallback(cb, { timeout: 4000 }) : setTimeout(cb, 2500));
    idle(() => { import("./tabs/MapTab"); import("./tabs/FleetTab"); import("./tabs/StoryTab"); });
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#story" onClick={(e) => { e.preventDefault(); go("story"); }}><span className="brand-mark" aria-hidden="true"><Route size={15} /></span><span>Route-to-<em>Impact</em></span></a>
        <nav className="tabs" role="tablist" aria-label="Sections" onKeyDown={(e) => {
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          const i = TABS.findIndex((t) => t.id === tab);
          const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length].id;
          go(next);
          (document.getElementById(`tab-${next}`) as HTMLButtonElement | null)?.focus();
        }}>
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} id={`tab-${id}`} role="tab" className="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => go(id)}>
              <Icon size={15} aria-hidden="true" /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="spacer" />
        <span className={`badge ${live ? "ok" : ""}`} title={live ? "Routing API connected" : "Showing precomputed demo data"}>
          <Circle size={8} fill="currentColor" aria-hidden="true" />{live === null ? "Connecting…" : live ? "Live engine" : "Demo data"}
        </span>
      </header>
      {TABS.filter((t) => visited.includes(t.id)).map(({ id, el: Tab }) => (
        <main key={id} className="stage" role="tabpanel" hidden={id !== tab} aria-hidden={id !== tab}>
          <TabBoundary>
            <Suspense fallback={<div className="stage loading">Loading…</div>}>
              <Tab active={id === tab} onNavigate={(to: string) => go(to as TabId)} />
            </Suspense>
          </TabBoundary>
        </main>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
