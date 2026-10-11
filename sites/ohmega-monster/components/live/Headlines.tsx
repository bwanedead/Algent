import { ago, type Headline } from "@/lib/live-shared";

// "What's happening now": 3-6 plain-language items computed by the backend from the feeds (no model). Tapping one centres the map.

const DOT: Record<Headline["layer"], string> = { outage: "#c4574a", quake: "#d9a521", fire: "#ea6a22", ships: "#2a8f9c", aircraft: "#8b6fd6" };

export default function Headlines({ items, asOf, now, onPick }: { items: Headline[]; asOf: string; now: number | null; onPick: (h: Headline) => void }) {
  return (
    <section className="live-now-strip" aria-label="What's happening now">
      <p className="live-now-title">
        What&apos;s happening now {asOf && now !== null && <span className="live-muted">· updated {ago(asOf, now)}</span>}
      </p>
      {items.length === 0 ? (
        <p className="live-empty">Nothing stands out against recent history right now.</p>
      ) : (
        <ul className="live-now-list">
          {items.map((h) => (
            <li key={h.id}>
              <button type="button" className="live-now-item" onClick={() => onPick(h)} disabled={h.lat === null || h.lon === null}>
                <span className="live-dotc" style={{ background: DOT[h.layer] }} aria-hidden="true" />
                <span>{h.text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
