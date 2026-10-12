// Client side of the tiled transport (backend live/tiles.py): which tiles a view needs, and a cache that refetches a tile only when
// its etag (from the index) changed. Pure and client-safe apart from the fetch it is handed.

import type { TileDoc, TileIndex } from "@/lib/live-shared";

import type { Entity } from "./entities";

export type LayerName = "vessels" | "aircraft";
export const FOLDER: Record<LayerName, string> = { vessels: "v", aircraft: "a" };
const MARGIN = 0.25; // of the view's size on each side: a short pan finds its tiles already loaded
const MAX_TILES = 24; // a hard bound on one layer's tiles in memory; the ones nearest the view's centre win

export const tileName = (row: number, col: number) => `r${String(row).padStart(2, "0")}c${String(col).padStart(2, "0")}`;

/** Ids of the index's tiles that intersect `bounds` ([west, south, east, north]) grown by a margin, nearest the centre first. */
export function wantedTiles(index: TileIndex, layer: LayerName, bounds: [number, number, number, number]): string[] {
  const deg = index.deg;
  const [w, s, e, n] = bounds;
  const dx = (e - w) * MARGIN, dy = (n - s) * MARGIN;
  const cols = Math.round(360 / deg), rows = Math.round(180 / deg);
  const c0 = Math.max(0, Math.floor((w - dx + 180) / deg)), c1 = Math.min(cols - 1, Math.floor((e + dx + 180) / deg));
  const r0 = Math.max(0, Math.floor((s - dy + 90) / deg)), r1 = Math.min(rows - 1, Math.floor((n + dy + 90) / deg));
  const cx = (w + e) / 2, cy = (s + n) / 2;
  const out: { id: string; d: number }[] = [];
  for (let r = r0; r <= r1; r++) {
    for (let c = c0; c <= c1; c++) {
      const id = tileName(r, c);
      if (index[layer]?.[id]) out.push({ id, d: Math.hypot((c + 0.5) * deg - 180 - cx, (r + 0.5) * deg - 90 - cy) });
    }
  }
  return out.sort((a, b) => a.d - b.d).slice(0, MAX_TILES).map((t) => t.id);
}

type Fetch = (name: string, opts: { v: string }) => Promise<TileDoc | null>;

/** The decoded objects of the tiles in view. `sync` fetches what is missing or whose etag moved and forgets tiles that left the view. */
export class TileCache {
  private tiles = new Map<string, { etag: string; ents: Entity[] }>();

  constructor(private layer: LayerName, private fetchTile: Fetch, private decode: (doc: TileDoc) => Entity[]) {}

  /** Returns true when the set of objects changed. A failed fetch keeps the tile's previous objects. */
  async sync(index: TileIndex, wanted: string[]): Promise<boolean> {
    let changed = false;
    for (const id of Array.from(this.tiles.keys())) {
      if (!wanted.includes(id)) {
        this.tiles.delete(id);
        changed = true;
      }
    }
    const stale = wanted.filter((id) => this.tiles.get(id)?.etag !== index[this.layer][id]?.[1]);
    await Promise.all(stale.map(async (id) => {
      const etag = index[this.layer][id][1];
      const doc = await this.fetchTile(`tiles/${FOLDER[this.layer]}/${id}`, { v: etag });
      if (doc) {
        this.tiles.set(id, { etag, ents: this.decode(doc) });
        changed = true;
      }
    }));
    return changed;
  }

  entities(wanted: string[]): Entity[] {
    return wanted.flatMap((id) => this.tiles.get(id)?.ents ?? []);
  }

  clear(): boolean {
    const had = this.tiles.size > 0;
    this.tiles.clear();
    return had;
  }
}
