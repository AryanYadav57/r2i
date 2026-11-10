# R2I v3 — UI Refinement & Performance Plan

> Follows `v2_implementation_plan.md`. Goal: a minimal, professional, fast app.
> No glassmorphism, no glows, no neon. Flat solid surfaces, one green accent,
> calm data colours, smooth 60 fps on every tab.

## Feedback this plan addresses

| Area | Problem |
|---|---|
| Story | Buildings too bright; congestion columns read as "green buildings"; mint body text hard to read; heavy frames |
| Map | Congestion columns on by default clutter the city; panels mix fonts (mono table + sans); A/B markers inconsistent; avoided-junction rings busy |
| Fleet | Vehicle routes too neon; timeline card cluttered (dots, no hour grid); raw keys like `2 van_diesel`; right panel repeats the headline and has long insight text |
| All | Slow first load and heavy rendering; hash links don't always switch tabs |

---

## Phase A — Design system (foundation for B–D)

- [ ] **Type:** Geist (UI, headlines) + Geist Mono (figures only), tabular numerals everywhere numbers change.
- [ ] **Surfaces:** one solid panel style: `#111916`, 1px `rgba(232,240,236,0.08)` border, 12px radius, no blur, no gradient, single soft shadow.
- [ ] **Data palette (muted, not neon):**
  - R2I `#4FA36B`, shortest/baseline `#C46A7E`, highlight amber `#D9A441`
  - Vehicles: `#6FA8C9 #6FBF9A #C9B46F #9C8FC9 #C98F6F #C47F9E #6FB5B0`
  - Lines get a dark casing (`#0B1210`, +2px) so they read without glowing.
- [ ] **Components:** `Panel` + `Section` (small header, divider), `Stat` (label above value), `CompareTable` (one font, aligned columns, Δ column), `Toggle` (switch row with label), `Stepper` (− n +), `Segmented`, `ListRow` (icon + one line + chevron). All icons from Lucide.
- [ ] **Remove:** remaining blur, glows, coloured shadows, emoji, duplicated headings.

**Done when:** every panel in the app is built from these components; no `backdrop-filter`, `radial-gradient` (except the Ask AI texture) or neon colours left.

---

## Phase B — Story tab

- [ ] Buildings dark slate `#2B3237`, opacity 0.9, vertical shading on, heights capped.
- [ ] Congestion: only top ~5% junctions, amber→red, slim (8 m radius) — no green prisms.
- [ ] Typography: Geist headlines (white, 800), body off-white 80%, green only for step label, figures and highlights; tabular CO₂ counter.
- [ ] Legibility: soft dark wash on the left third only (no visible edges, no card).
- [ ] Render only what a step needs: buildings steps 1–2, columns 2–3, race 3–4, fleet 5; fully faded layers not drawn.
- [ ] Per-frame card fades and progress bar written via refs (no React re-render per frame); static text memoised.

**Done when:** text readable over any frame; steady 60 fps on a production build at 1920×1080.

---

## Phase C — Map tab

- [ ] Default view: congestion off; when on, top ~5% amber/red slim markers; full gradient layer behind an "All junctions" toggle.
- [ ] **Left panel** sections: *Route* (search, A/B fields with swap), *Vehicle* (select with icon), *Preference* (α slider with "Faster ↔ Cleaner" labels), *Layers* (toggles: congestion, avoided junctions), *Animate* (Race, Dijkstra wave, Trade-off).
- [ ] **Right panel:** three stats (CO₂ %, idling saved, ₹ saved) → `CompareTable` → "Avoided junctions" top 3 with severity bar + idle time, "Show more".
- [ ] Proper A/B pin markers; R2I line 5px with casing, shortest 4px muted; avoided-junction markers small amber dots.
- [ ] Trade-off chart restyled to the data palette, inline in the right panel.

**Done when:** one font family per role, no mono labels, map readable with all layers on.

---

## Phase D — Fleet tab

- [ ] **Map:** muted vehicle palette with casing; default *R2I only*, distance-only plan as a toggle (thin dashed `#C46A7E`); selecting a vehicle dims others to 15%; stops as small numbered dots; hub as a clear square marker.
- [ ] **Left panel:** step `Segmented` (Plan / Simulate / Report); vehicle list rows (Lucide icon by type, readable name "Diesel van", capacity, stops "23 → 1"); *New scenario* collapsible with seed, orders and `Stepper`s per vehicle type using readable labels; Re-plan button.
- [ ] **Right panel:** three stats (₹ saved, CO₂ saved, fuel saved) → insights as `ListRow`s (icon + one-line title, detail on expand, click flies map) → `CompareTable`. No repeated headline.
- [ ] **Timeline card:** player row (play/pause, clock, speed `Segmented`, scrubber); Gantt with hour gridlines + labels (09:00…13:00), thin activity bars, stops as small ticks (not dots), late stops in amber, vehicle labels with colour chip, hover tooltip (order, time, load); collapsible to the player row only.
- [ ] Clock/Gantt DOM updates at ~10 fps; map animates at 60 fps.

**Done when:** routes calm and distinguishable, timeline readable at a glance, no raw keys in UI.

---

## Phase E — Performance (all tabs)

1. [ ] `npm run preview:prod` (build + `vite preview`); all measurements on it, with the browser pane visible.
2. [ ] Cap pixel ratio at 1.5 for MapLibre (`pixelRatio`) and deck (`useDevicePixels: 1.5`).
3. [ ] Smaller tile cache; buildings only where shown (Story).
4. [ ] `preset.json` 534 KB → < 150 KB (delta-encoded trajectories, 5-decimal coords, drop unused fields).
5. [ ] Preload map style + fonts; fade the map in on `load` (no black flash); idle-time prefetch of the next likely tab.
6. [ ] Fix hash navigation so `#map`, `#fleet`… always switch tabs.
7. [ ] Targets (prod build, 1920×1080): first map visible < 1.5 s, tab switch < 150 ms, 60 fps during Story scroll and Fleet simulation.

**Optional E2:** self-hosted Bengaluru PMTiles (~15–25 MB) for instant, offline-safe tiles — only if targets are missed after E1–E7.

---

## Phase F — Consistency pass

- [ ] Ask AI and Method tabs moved onto the Phase A components (Ask AI keeps its subtle green texture).
- [ ] Screenshot review of every tab at 1920×1080 and 375 px mobile.
- [ ] README screenshots/GIF refreshed.

## Order

A → B → C → D → E → F. A is small but everything else depends on it; E's measurements run after each of B–D so regressions show up early.
