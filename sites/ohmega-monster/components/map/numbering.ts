import type { TheaterMap } from "@/lib/daily";

/** The map's numbers index the developments. Zero-based unless the data plainly counts from 1. */
export function mapIndexBase(map: TheaterMap, devCount: number): 0 | 1 {
  const ns = map.points.map((p) => p.n).filter((n): n is number => n !== null);
  return !ns.includes(0) && ns.includes(devCount) ? 1 : 0;
}

/** Development index -> the number the map marks it with (1-based). */
export function mappedNumbers(map: TheaterMap | null, devCount: number): Map<number, number> {
  const out = new Map<number, number>();
  if (!map) return out;
  const base = mapIndexBase(map, devCount);
  for (const p of map.points) if (p.n !== null && p.n - base >= 0 && p.n - base < devCount) out.set(p.n - base, p.n - base + 1);
  return out;
}
