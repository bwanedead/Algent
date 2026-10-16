import Link from "next/link";

import type { DailyChangeKind, DailyTheater } from "@/lib/daily";
import { claimOf, headlineOf, shortDay, splitLead } from "@/lib/daily";
import { dossierPath } from "@/lib/dossier";
import { eventPath } from "@/lib/entities";
import type { TheaterInfra } from "@/lib/geoledger";
import { GLOSSARY } from "@/lib/glossary";
import type { Direction, Snapshot } from "@/lib/intel";

import AssetStatusLog, { logLines } from "./AssetStatusLog";
import GridImpact from "./GridImpact";
import { countryName } from "@/lib/flags";
import DailyFigure from "./DailyFigure";
import LinkedText from "./entities/LinkedText";
import Expander from "./Expander";
import OnRecordBlock from "./OnRecord";
import Term from "./Term";
import { DevelopmentTimeline, KeyFigures, PulseTiles, SourceLink } from "./DailyVisuals";
import LiveNowStrip from "./live/LiveNowStrip";
import GeoMap from "./map/GeoMap";
import TheaterNumbersPanel from "./numbers/TheaterNumbers";
import "@/app/intel/theaters/theaters.css";

// One theater of the daily report. Open, a skimmer gets: the claim, the picture (the desk's own visual first,
// then the map and stat tiles) and the top three developments. Everything else waits behind labelled expanders.

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

const TOP_SHOWN = 3; // developments visible without opening anything

function ContextList({ t }: { t: DailyTheater }) {
  return (
    <ul className="geo-ctx">
      {t.context.map((c, k) => (
        <li key={k}>
          <span className="geo-micro geo-ctx-when">{/^\d{4}-\d{2}-\d{2}$/.test(c.when) ? shortDay(c.when) + " " + c.when.slice(0, 4) : c.when || "Earlier"}</span>
          <span>
            <span className="geo-ctx-what"><LinkedText text={c.what} /></span>
            {c.why_relevant && <span className="geo-muted"> <LinkedText text={c.why_relevant} /></span>}
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

const NO_INFRA: TheaterInfra = { assets: [], log: [], grid: null };

export default function DailyTheaterSection({ t, id, date, snap, dossiers, first = false, tag = "", update = false, background = "", infra = NO_INFRA, events = false }: { t: DailyTheater; id: string; date: string; snap: Snapshot | null; dossiers: ReadonlySet<string>; first?: boolean; tag?: string; update?: boolean; background?: string; infra?: TheaterInfra; events?: boolean }) {
  const statusLog = logLines(infra.log, t.asset_events);
  const dir = DIR[t.escalation.direction];
  const claim = headlineOf(t.headline, t.bottom_line, 150) || claimOf(t.since_yesterday[0]?.what ?? "", 150) || t.name;
  const changed = t.since_yesterday.filter((c) => c.kind !== "unchanged");
  const same = t.since_yesterday.filter((c) => c.kind === "unchanged");
  const outlook = t.outlook.trim();
  const watch = t.watch_next;
  const hasNumbers = !!t.numbers && (t.numbers.trackers.length > 0 || t.numbers.actors.length > 0);
  const unusual = t.numbers ? t.numbers.trackers.filter((x) => x.unusual && x.new).length : 0;
  const hasMap = t.map !== null;
  const hasFigs = t.key_figures.length > 0;
  const dossierHref = dossierPath(t.theater_id, dossiers);
  const eventOf = events && !update ? (n: number) => eventPath(date, t.theater_id, n) : undefined;

  return (
    <section id={id} className={`geo-theater${update ? " is-update" : ""}`} aria-labelledby={`${id}-claim`}>
      <header className="geo-th">
        <p className="geo-kicker">
          {update && <span className="geo-edition-tag">Update</span>}
          {tag && <span className="geo-edition-tag">{tag}</span>}
          <span>
            {dossierHref ? (
              <Link href={dossierHref} className="th-dlink" title="Open this theater's dossier: background, actors, record, outlook">
                {t.name}
                <span className="th-dlink-go"> · dossier →</span>
              </Link>
            ) : (
              t.name
            )}
          </span>
          <span className={`geo-dir${dir.moving ? " is-moving" : ""}`}>
            <span aria-hidden="true">{dir.glyph}</span>{" "}
            <Term id="direction" label="direction">
              {dir.word}
            </Term>
            <span className="geo-sr">, {t.escalation.pace} pace</span>
          </span>
        </p>
        <h2 id={`${id}-claim`} className="geo-claim">
          {claim}
        </h2>
        {(t.saga || background) && !update && <p className="geo-saga"><LinkedText text={t.saga || background} /></p>}
      </header>

      <LiveNowStrip scope={id} bbox={t.map?.bbox} />

      {t.visuals.map((v) => (
        <DailyFigure key={v.id} v={v} />
      ))}

      {(hasMap || hasFigs) && (
        <div className={`geo-visual${hasMap && hasFigs ? " is-two" : ""}`}>
          <GeoMap map={t.map} developments={t.developments} liveScope={id} assets={infra.assets} assetLog={infra.log} />
          <KeyFigures figures={t.key_figures} />
        </div>
      )}

      {infra.grid && <GridImpact grid={infra.grid} name={countryName(infra.grid.iso)} />}

      <DevelopmentTimeline developments={t.developments} map={t.map} reportDate={date} range={[0, TOP_SHOWN]} anchor={id} eventHref={eventOf} />

      <div className="geo-exps">
        <Expander label="Assessment and what changed" hint="the full read, since yesterday">
          <p className="geo-pd-text"><LinkedText text={t.bottom_line} /></p>
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
                          <LinkedText text={claimOf(tail, 130)} />
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
              {same.length > 0 && (
                <p className="geo-micro">
                  <span aria-hidden="true">=</span> {changed.length === 0 ? "Nothing changed since yesterday" : `${same.length} unchanged`}: {same.map((c) => c.what).join(" · ")}
                </p>
              )}
            </div>
          )}
        </Expander>

        {t.developments.length > TOP_SHOWN && (
          <Expander label="More developments" count={t.developments.length - TOP_SHOWN}>
            <DevelopmentTimeline developments={t.developments} map={t.map} reportDate={date} range={[TOP_SHOWN, t.developments.length]} anchor={id} eventHref={eventOf} />
          </Expander>
        )}

        {t.on_record.length > 0 && (
          <Expander label="On the record" count={t.on_record.length} hint="what was said, in the speakers' words">
            <OnRecordBlock rows={t.on_record} title={t.name} note={first} />
          </Expander>
        )}

        {statusLog.length > 0 && (
          <Expander label="Strike & status log" count={statusLog.length} hint="named places, who says what, this week">
            <AssetStatusLog lines={statusLog} />
          </Expander>
        )}

        {hasNumbers && (
          <Expander label="Numbers and actors" hint={unusual > 0 ? `${unusual} unusual now` : "statistics, flows and rates"}>
            <TheaterNumbersPanel numbers={t.numbers} name={t.name} />
          </Expander>
        )}

        {t.pulses.length > 0 && (
          <Expander label="Pulses" count={t.pulses.length} hint="how tense, 0 to 100">
            <p className="geo-gloss">{GLOSSARY.pulse}</p>
            <PulseTiles pulses={t.pulses} snap={snap} />
          </Expander>
        )}

        {(outlook || watch.length > 0 || t.context.length > 0 || t.brief_slug) && (
          <Expander label="Outlook, watch list and background">
            {t.outlook && (
              <p className="geo-next-outlook">
                <span className="geo-micro">Outlook</span> <LinkedText text={t.outlook} />
              </p>
            )}
            {t.watch_next.length > 0 && (
              <div>
                <span className="geo-micro">Watch for</span>
                <ul className="geo-plain">
                  {t.watch_next.map((w, k) => (
                    <li key={k}><LinkedText text={w} /></li>
                  ))}
                </ul>
              </div>
            )}
            {t.context.length > 0 && (
              <div>
                <span className="geo-micro">Background</span>
                <ContextList t={t} />
              </div>
            )}
            {t.brief_slug && (
              <p className="geo-pd-foot">
                <Link href={`/intel/briefs/${t.brief_slug}`}>Deep brief →</Link>
              </p>
            )}
          </Expander>
        )}
      </div>
    </section>
  );
}
