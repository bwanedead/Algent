import Link from "next/link";

import Popover from "@/components/Popover";
import type { DailyChangeKind, DailyTheater } from "@/lib/daily";
import { claimOf, isCut, shortDay, splitLead } from "@/lib/daily";
import type { Direction, Snapshot } from "@/lib/intel";

import { DevelopmentTimeline, KeyFigures, PulseTiles, SourceLink, TheaterMapFigure } from "./DailyVisuals";

// One theater of the daily report. Reading order: the claim (bottom line up front), the picture
// (map + figures), what changed, what happened, the Pulses, what next. Detail waits in popovers.

/** The accent colours change: only escalated and new wear it (`hot`). */
const CHANGE: Record<DailyChangeKind, { glyph: string; label: string; hot: boolean }> = {
  escalated: { glyph: "▲", label: "Escalated", hot: true },
  new: { glyph: "●", label: "New", hot: true },
  eased: { glyph: "▼", label: "Eased", hot: false },
  resolved: { glyph: "✓", label: "Resolved", hot: false },
  unchanged: { glyph: "=", label: "Unchanged", hot: false },
};

const DIR: Record<Direction, { glyph: string; word: string; moving: boolean }> = {
  rising: { glyph: "▲", word: "rising", moving: true },
  steady: { glyph: "◆", word: "steady", moving: false },
  easing: { glyph: "▼", word: "easing", moving: true },
  unclear: { glyph: "?", word: "unclear", moving: false },
};

const WATCH_SHOWN = 3;

function ContextList({ t }: { t: DailyTheater }) {
  return (
    <ul className="geo-ctx">
      {t.context.map((c, k) => (
        <li key={k}>
          <span className="geo-micro geo-ctx-when">{/^\d{4}-\d{2}-\d{2}$/.test(c.when) ? shortDay(c.when) + " " + c.when.slice(0, 4) : c.when || "Earlier"}</span>
          <span>
            <span className="geo-ctx-what">{c.what}</span>
            {c.why_relevant && <span className="geo-muted"> {c.why_relevant}</span>}
            {c.source && (
              <>
                {" "}
                <SourceLink url={c.source} />
              </>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function DailyTheaterSection({ t, id, date, snap }: { t: DailyTheater; id: string; date: string; snap: Snapshot | null }) {
  const dir = DIR[t.escalation.direction];
  const claim = claimOf(t.bottom_line, 150) || claimOf(t.since_yesterday[0]?.what ?? "", 150) || t.name;
  const changed = t.since_yesterday.filter((c) => c.kind !== "unchanged");
  const same = t.since_yesterday.filter((c) => c.kind === "unchanged");
  const outlook = claimOf(t.outlook, 170);
  const watch = t.watch_next.map((w) => claimOf(w, 95));
  const outlookCut = isCut(t.outlook, outlook) || t.watch_next.length > WATCH_SHOWN || t.watch_next.some((w, k) => isCut(w, watch[k]));
  const hasMap = t.map !== null;
  const hasFigs = t.key_figures.length > 0;

  return (
    <section id={id} className="geo-theater" aria-labelledby={`${id}-claim`}>
      <header className="geo-th">
        <p className="geo-kicker">
          <span>{t.name}</span>
          <span className={`geo-dir${dir.moving ? " is-moving" : ""}`} title={`Is the situation itself getting worse or easing: ${dir.word}, ${t.escalation.pace} pace`}>
            <span aria-hidden="true">{dir.glyph}</span> {dir.word}
          </span>
        </p>
        <h2 id={`${id}-claim`} className="geo-claim">
          {claim}
        </h2>
        {isCut(t.bottom_line, claim) && (
          <Popover label={`Full assessment: ${t.name}`} triggerClassName="geo-link-btn" trigger={<>Full assessment ›</>}>
            <div className="geo-pd">
              <p className="geo-pd-title">{t.name}</p>
              <p className="geo-pd-text">{t.bottom_line}</p>
            </div>
          </Popover>
        )}
      </header>

      {(hasMap || hasFigs) && (
        <div className={`geo-visual${hasMap && hasFigs ? " is-two" : ""}`}>
          <TheaterMapFigure map={t.map} developments={t.developments} />
          <KeyFigures figures={t.key_figures} />
        </div>
      )}

      {t.since_yesterday.length > 0 && (
        <div className="geo-since">
          {changed.length > 0 && (
            <ul className="geo-chrows">
              {changed.map((c, k) => {
                const ch = CHANGE[c.kind];
                const { lead, tail } = splitLead(c.what);
                return (
                  <li key={k} className={ch.hot ? "is-hot" : ""} title={c.what}>
                    <span className="geo-glyph" aria-hidden="true">
                      {ch.glyph}
                    </span>
                    <span className="geo-sr">{ch.label}: </span>
                    <span>
                      {lead && <b className="geo-strong">{lead} </b>}
                      {claimOf(tail, 130)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          {same.length > 0 && (
            <Popover
              label={`Unchanged since yesterday: ${same.length}`}
              triggerClassName="geo-link-btn geo-same"
              trigger={
                <>
                  <span aria-hidden="true">=</span> {changed.length === 0 ? "Nothing changed since yesterday" : `${same.length} unchanged`} ›
                </>
              }
            >
              <div className="geo-pd">
                <p className="geo-pd-title">Unchanged since yesterday</p>
                <ul className="geo-plain">
                  {same.map((c, k) => (
                    <li key={k}>{c.what}</li>
                  ))}
                </ul>
              </div>
            </Popover>
          )}
        </div>
      )}

      <DevelopmentTimeline developments={t.developments} map={t.map} reportDate={date} />

      <PulseTiles pulses={t.pulses} snap={snap} />

      {(outlook || watch.length > 0) && (
        <div className="geo-next">
          {outlook && (
            <p className="geo-next-outlook">
              <span className="geo-micro">Outlook</span> {outlook}
            </p>
          )}
          {watch.length > 0 && (
            <div>
              <span className="geo-micro">Watch for</span>
              <ul className="geo-watch">
                {watch.slice(0, WATCH_SHOWN).map((w, k) => (
                  <li key={k} title={t.watch_next[k]}>
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {outlookCut && (
            <Popover label={`Full outlook: ${t.name}`} triggerClassName="geo-link-btn" trigger={<>Full outlook and watch list ›</>}>
              <div className="geo-pd">
                <p className="geo-pd-title">{t.name}</p>
                {t.outlook && <p className="geo-pd-text">{t.outlook}</p>}
                {t.watch_next.length > 0 && (
                  <>
                    <p className="geo-micro">Watch for</p>
                    <ul className="geo-plain">
                      {t.watch_next.map((w, k) => (
                        <li key={k}>{w}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </Popover>
          )}
        </div>
      )}

      {(t.context.length > 0 || t.brief_slug) && (
        <Popover
          label={`Background: ${t.name}`}
          triggerClassName="geo-link-btn"
          trigger={<>{t.context.length > 0 ? `Background (${t.context.length})` : "Deep brief"} ›</>}
        >
          <div className="geo-pd">
            <p className="geo-pd-title">{t.name}</p>
            {t.context.length > 0 && <ContextList t={t} />}
            {t.brief_slug && (
              <p className="geo-pd-foot">
                <Link href={`/intel/briefs/${t.brief_slug}`}>Deep brief →</Link>
              </p>
            )}
          </div>
        </Popover>
      )}
    </section>
  );
}
