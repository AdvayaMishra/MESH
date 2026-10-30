"use client";
import * as React from "react";
import { useReducedMotion } from "framer-motion";

export function useCountUp(target: number, duration = 900) {
  const reduce = useReducedMotion();
  const [value, setValue] = React.useState(0);
  React.useEffect(() => {
    if (reduce) return;
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      setValue(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, reduce]);
  return reduce ? target : value;
}
