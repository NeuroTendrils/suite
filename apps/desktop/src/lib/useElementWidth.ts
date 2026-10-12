import { useCallback, useRef, useState } from "react";

/** Track an element's content width so SVG plots can fill their container. */
export function useElementWidth<T extends HTMLElement>(fallback: number): [(el: T | null) => void, number] {
  const [width, setWidth] = useState(fallback);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el) return;
    const measure = () => {
      const w = Math.floor(el.clientWidth);
      if (w > 0) setWidth(w);
    };
    measure();
    observer.current = new ResizeObserver(measure);
    observer.current.observe(el);
  }, []);
  return [ref, width];
}
