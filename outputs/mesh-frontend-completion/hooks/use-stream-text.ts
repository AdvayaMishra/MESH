"use client";
import * as React from "react";
import { useReducedMotion } from "framer-motion";

/** Simulates token streaming. Respects reduced-motion by revealing text immediately. */
export function useStreamText() {
  const reduce = useReducedMotion();
  const [text, setText] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = React.useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  }, []);

  const start = React.useCallback(
    (full: string, onDone?: () => void) => {
      stop();
      if (reduce) {
        setText(full);
        setStreaming(false);
        onDone?.();
        return;
      }
      setText("");
      setStreaming(true);
      const words = full.split(" ");
      let i = 0;
      timer.current = setInterval(() => {
        i += 2;
        setText(words.slice(0, i).join(" "));
        if (i >= words.length) {
          stop();
          setStreaming(false);
          onDone?.();
        }
      }, 45);
    },
    [reduce, stop]
  );

  React.useEffect(() => stop, [stop]);
  const reset = React.useCallback(() => {
    stop();
    setText("");
    setStreaming(false);
  }, [stop]);
  return { text, streaming, start, reset };
}
