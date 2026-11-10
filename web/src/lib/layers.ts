// Loosely-typed re-exports of the deck.gl layers used here: accessor return
// types (Color, Position) are plain number[] in this codebase.
import * as D from "deck.gl";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = new (props: Record<string, any>) => D.Layer;
export const PathLayer = D.PathLayer as unknown as Loose;
export const ScatterplotLayer = D.ScatterplotLayer as unknown as Loose;
export const ColumnLayer = D.ColumnLayer as unknown as Loose;
export const TripsLayer = D.TripsLayer as unknown as Loose;

/**
 * A path drawn over a dark casing so it reads on the basemap without glowing.
 * Returns [casing, line]; pass the same props you would give a PathLayer.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function casedPath(props: Record<string, any>, casing: [number, number, number] = [11, 18, 16]): D.Layer[] {
  const w = props.widthMinPixels ?? 3;
  return [
    new PathLayer({ ...props, id: `${props.id}-casing`, getColor: [...casing, 220], widthMinPixels: w + 3, pickable: false,
      updateTriggers: {} }),
    new PathLayer({ ...props, capRounded: true, jointRounded: true }),
  ];
}
export const TextLayer = D.TextLayer as unknown as Loose;
