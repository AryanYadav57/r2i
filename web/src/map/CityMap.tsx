import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { MapboxOverlay } from "@deck.gl/mapbox";
import "maplibre-gl/dist/maplibre-gl.css";

// Free vector tiles, no API key (OpenFreeMap).
const STYLE = "https://tiles.openfreemap.org/styles/dark";
// High-DPI screens render up to 4x the pixels; 1.5x looks the same on a map and costs far less.
const DPR = typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio || 1, 1.5);

export const BENGALURU: MapViewState = {
  longitude: 77.622, latitude: 12.935, zoom: 13.2, pitch: 35, bearing: -12,
};

/**
 * Camera options with only the fields that have values. MapLibre checks `"bearing" in options`, so an
 * explicit `undefined` becomes NaN, breaks the camera matrix ("failed to invert matrix") and stops rendering.
 */
function cameraOf(t: FlyTarget) {
  const o: { center: [number, number]; zoom?: number; pitch?: number; bearing?: number } = { center: [t.longitude, t.latitude] };
  if (Number.isFinite(t.zoom)) o.zoom = t.zoom;
  if (Number.isFinite(t.pitch)) o.pitch = t.pitch;
  if (Number.isFinite(t.bearing)) o.bearing = t.bearing;
  return o;
}

export interface FlyTarget { longitude: number; latitude: number; zoom?: number; pitch?: number; bearing?: number }

interface Props {
  layers: Layer[];
  initial?: MapViewState;
  flyTo?: FlyTarget | null;
  onClick?: (info: PickingInfo) => void;
  getTooltip?: (info: PickingInfo) => string | null;
  buildings?: boolean;
  interactive?: boolean;
  /** Show/hide the 3D building layer without reloading it. */
  buildingsVisible?: boolean;
  /** Zoom from which buildings render (Story shows them from further out). */
  buildingsMinZoom?: number;
  /** Controlled camera (e.g. scroll-driven): applied with jumpTo each change. */
  viewState?: MapViewState;
}

/**
 * MapLibre map created imperatively (no React wrapper) with deck.gl attached as an overlay
 * synced to its camera. React re-renders only update deck layers, never the map camera, so
 * renders during a camera animation can't corrupt MapLibre's transform.
 */
export default function CityMap({ layers, initial = BENGALURU, flyTo, onClick, getTooltip, buildings = false,
  interactive = true, buildingsVisible = true, buildingsMinZoom = 15, viewState }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const pendingFly = useRef<FlyTarget | null>(null);
  const [ready, setReady] = useState(false);

  // Create once.
  useEffect(() => {
    const start = viewState ?? initial;
    const map = new maplibregl.Map({
      container: el.current!, style: STYLE, center: [start.longitude, start.latitude], zoom: start.zoom,
      pitch: start.pitch ?? 0, bearing: start.bearing ?? 0, minZoom: 11, maxZoom: 18,
      // Story uses steep cinematic angles; elsewhere cap the tilt so the horizon never shows unloaded void.
      maxPitch: viewState ? 75 : 60,
      pixelRatio: DPR, fadeDuration: 0, attributionControl: false, refreshExpiredTiles: false,
      interactive: interactive && !viewState, dragRotate: true,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    const overlay = new MapboxOverlay({ interleaved: false, useDevicePixels: DPR, layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    map.once("render", () => setReady(true));
    const fallback = setTimeout(() => setReady(true), 1200);   // never leave the map invisible
    map.on("load", () => {
      const f = pendingFly.current;
      if (f) { map.jumpTo(cameraOf(f)); pendingFly.current = null; }
      if (!buildings || map.getLayer("r2i-buildings")) return;
      const source = Object.keys(map.getStyle().sources).find((s) => s.includes("openmaptiles")) ?? "openmaptiles";
      try {
        map.addLayer({
          id: "r2i-buildings", type: "fill-extrusion", source, "source-layer": "building", minzoom: buildingsMinZoom,
          paint: {
            "fill-extrusion-color": "#2b3237",
            "fill-extrusion-height": ["min", 24, ["coalesce", ["get", "render_height"], 8]],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": 0.9,
            "fill-extrusion-vertical-gradient": true,
          },
        });
      } catch { /* style without building data: skip */ }
    });
    // Keep the canvas matched to its container (tab shown, panel layout, window or DPR changes).
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el.current!);
    if (import.meta.env.DEV) ((window as unknown as { __maps?: maplibregl.Map[] }).__maps ??= []).push(map);   // dev-only inspection hook
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => { ro.disconnect(); clearTimeout(fallback); map.remove(); mapRef.current = null; overlayRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Layers, picking and tooltips: cheap, every render.
  useEffect(() => {
    overlayRef.current?.setProps({
      layers, onClick,
      getTooltip: getTooltip ? (info: PickingInfo) => { const t = getTooltip(info); return t ? { text: t } : null; } : undefined,
      getCursor: ({ isHovering }: { isHovering: boolean }) => (isHovering ? "pointer" : onClick ? "crosshair" : "grab"),
    });
  });

  // Controlled camera (Story).
  useEffect(() => {
    if (!viewState || !mapRef.current) return;
    mapRef.current.jumpTo({ center: [viewState.longitude, viewState.latitude], zoom: viewState.zoom,
      pitch: viewState.pitch ?? 0, bearing: viewState.bearing ?? 0 });
  }, [viewState?.longitude, viewState?.latitude, viewState?.zoom, viewState?.pitch, viewState?.bearing]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Fly requests.
  useEffect(() => {
    if (!flyTo) return;
    const map = mapRef.current;
    if (!map) { pendingFly.current = flyTo; return; }
    map.flyTo({ ...cameraOf(flyTo), duration: 1600, essential: true });
  }, [flyTo]);

  // Building visibility per step.
  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("r2i-buildings")) map.setLayoutProperty("r2i-buildings", "visibility", buildingsVisible ? "visible" : "none");
  }, [buildingsVisible]);

  return <div ref={el} className="citymap" style={{ position: "absolute", inset: 0, opacity: ready ? 1 : 0, transition: "opacity 0.5s ease" }} />;
}
