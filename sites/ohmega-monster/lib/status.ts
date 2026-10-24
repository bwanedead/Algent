import { tableDoc, TTL } from "./store";

// Per-product status files (backend ops/status.py, published at `docs/status/<product>.json.gz`, schema ohmega.status/1): written at the end of every
// successful run of a product's job, whether or not it published anything new. They separate two questions the data's own `as_of` mixes up:
//   checked_at       "is it alive":    the end of the last successful run. Late for the product's cadence = the product has stopped.
//   last_changed_at  "what's new":     the last time a run actually uploaded a new object. A quiet product (no new sanctions designation) keeps an old one.
// Hubs judge staleness on checked_at and show last_changed_at as the age. Absent (not published yet): both are "", and the data's own stamp is used.

export type ProductStatus = { checked_at: string; last_changed_at: string };

export async function productStatus(id: string): Promise<ProductStatus | null> {
  if (!/^[a-z_]+$/.test(id)) return null;
  const doc = await tableDoc<{ checked_at?: unknown; last_changed_at?: unknown }>(`status/${id}.json`, TTL.fast);
  if (!doc || typeof doc.checked_at !== "string" || doc.checked_at === "") return null;
  return { checked_at: doc.checked_at, last_changed_at: typeof doc.last_changed_at === "string" ? doc.last_changed_at : "" };
}

/** The statuses of several products at once (a missing one is simply absent). */
export async function productStatuses(ids: string[]): Promise<Record<string, ProductStatus>> {
  const rows = await Promise.all(ids.map(async (id) => [id, await productStatus(id)] as const));
  return Object.fromEntries(rows.filter((r): r is readonly [string, ProductStatus] => r[1] !== null));
}

/** What a door shows for a product: `stamp` is what's new (the later of the data's own stamp and the last change), `checked` is when it was last verified alive. */
export function withStatus(stamp: string, st: ProductStatus | undefined): { stamp: string; checked?: string } {
  if (!st) return { stamp };
  const changed = st.last_changed_at && st.last_changed_at > stamp ? st.last_changed_at : stamp;
  return { stamp: changed || st.checked_at, checked: st.checked_at };
}
