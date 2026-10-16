"use client";

// Fetches a native visual's data spec in the browser (our published assets) once its host nears the viewport, and parses it.
// Shared by the native figures (NativeNetwork, NativeFlow, NativeTrackerCompare): `host` goes on the wrapper element, `spec` is
// the parsed data, `failed` means the fetch or the parse failed (the caller then shows its server-drawn still). Client-safe.

import { useEffect, useRef, useState, type RefObject } from "react";

export function useSpec<T>(src: string, parse: (raw: unknown) => T | null): { host: RefObject<HTMLDivElement>; spec: T | null; failed: boolean } {
  const host = useRef<HTMLDivElement>(null);
  const [go, setGo] = useState(false);
  const [spec, setSpec] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setGo(true);
      return;
    }
    const io = new IntersectionObserver(
      (es) => {
        if (es.some((e) => e.isIntersecting)) {
          setGo(true);
          io.disconnect();
        }
      },
      { rootMargin: "400px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!go) return;
    let dead = false;
    fetch(src)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j) => {
        if (dead) return;
        const s = parse(j);
        if (s) setSpec(s);
        else setFailed(true);
      })
      .catch(() => !dead && setFailed(true));
    return () => {
      dead = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `parse` is a module-level function of the caller
  }, [go, src]);

  return { host, spec, failed };
}
