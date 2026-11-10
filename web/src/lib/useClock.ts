import { useEffect, useRef, useState } from "react";

/** Animation clock in "scenario seconds": advances `speed` scenario-seconds per real second. */
export function useClock(start: number, end: number, speed: number, playing: boolean, loop = false) {
  const [t, setT] = useState(start);
  const last = useRef<number | null>(null);

  useEffect(() => setT(start), [start]);

  useEffect(() => {
    if (!playing) { last.current = null; return; }
    let raf = 0;
    const tick = (now: number) => {
      const dt = last.current === null ? 0 : (now - last.current) / 1000;
      last.current = now;
      setT((prev) => {
        const next = prev + dt * speed;
        if (next >= end) return loop ? start : end;
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, start, end, loop]);

  return [t, setT] as const;
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
