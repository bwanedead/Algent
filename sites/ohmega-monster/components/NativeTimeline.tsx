"use client";

// The native timeline (daily visual kind "timeline" with a `spec`; contract: backend agents/intel/timeline_spec.py).
// Built to be read top to bottom on a phone: a date column, ONE continuous spine, and a readable card per event
// (bold title, muted detail, who, what kind, tap for sources). Time is made visible by the gaps between rows
// (timelineLayout.ts: proportional for a week, compressed after, named "· 6 days ·"). Lanes appear only when the desk
// found parallel threads, as a coloured card edge and a filter chip. The event list IS the text alternative.
// The spec is fetched in the browser from our published assets; any failure falls back to the server-drawn still.
// Client-safe imports only.

import { useEffect, useRef, useState, type ReactNode } from "react";

import IsoFlags from "@/components/IsoFlags";
import { dateParts, layoutRows, type Row } from "@/components/timelineLayout";
import { parseTimeline, type SpecSource, type TimelineKind, type TimelineSpec } from "@/lib/visualSpecs";

import "./timeline.css";

const KIND_LABEL: Record<TimelineKind, string> = {
  strike: "Strike",
  statement: "Statement",
  meeting: "Meeting",
  decision: "Decision",
  movement: "Movement",
  deadline: "Deadline",
  other: "Event",
};

// One 12px glyph per kind, drawn with the text colour; the kind is always also written beside it.
const GLYPH: Record<TimelineKind, ReactNode> = {
  strike: <path d="M6 1v3M6 8v3M1 6h3M8 6h3M2.6 2.6l1.9 1.9M7.5 7.5l1.9 1.9M9.4 2.6L7.5 4.5M4.5 7.5L2.6 9.4" />,
  statement: <path d="M1.5 2h9v6h-5L3 10.5V8H1.5z" />,
  meeting: (
    <>
      <circle cx="4.5" cy="6" r="3" />
      <circle cx="7.5" cy="6" r="3" />
    </>
  ),
  decision: <path d="M2.5 1v10M2.5 2h7L8 4.5 9.5 7h-7" />,
  movement: <path d="M1 6h9M7 3l3 3-3 3" />,
  deadline: (
    <>
      <circle cx="6" cy="6" r="4.6" />
      <path d="M6 3.4V6l2 1.4" />
    </>
  ),
  other: <circle cx="6" cy="6" r="1.8" />,
};

function Glyph({ kind }: { kind: TimelineKind }) {
  return (
    <svg className="nt-glyph" viewBox="0 0 12 12" width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {GLYPH[kind]}
    </svg>
  );
}

const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

function Sources({ sources, place }: { sources: SpecSource[]; place: string }) {
  if (sources.length === 0 && !place) return null;
  const n = sources.length;
  return (
    <details className="nt-more">
      <summary>{[place, n ? `${n} source${n === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ")}</summary>
      <ul>
        {sources.map((s, i) => (
          <li key={i}>
            {s.url ? (
              <a href={s.url} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">
                {s.label || hostOf(s.url)} ↗
              </a>
            ) : (
              <span className="geo-micro">{s.label}</span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function EventRow({ row, laneIndex, laneLabel, dim }: { row: Extract<Row, { kind: "event" }>; laneIndex: number; laneLabel: string; dim: boolean }) {
  const e = row.event;
  const d = dateParts(e.date);
  return (
    <li className={`nt-row nt-event k-${e.kind}${row.first ? " is-first" : ""}${row.last ? " is-last" : ""}${dim ? " is-dim" : ""}`}>
      <div className="nt-date">
        {row.showDate && (
          <>
            <b>{d.day}</b>
            <span>{d.weekday}</span>
          </>
        )}
        {e.time && <span className="nt-time">{e.time}</span>}
      </div>
      <div className="nt-spine" aria-hidden="true">
        <span className="nt-dot">
          <Glyph kind={e.kind} />
        </span>
      </div>
      <div className={`nt-card${laneIndex >= 0 ? ` has-lane l${laneIndex}` : ""}`}>
        <p className="nt-meta">
          <span className="nt-kind">{KIND_LABEL[e.kind]}</span>
          {laneLabel && <span className="nt-lane">{laneLabel}</span>}
          <IsoFlags codes={e.actors} link />
        </p>
        <p className="nt-title">{e.title}</p>
        {e.detail && <p className="nt-detail">{e.detail}</p>}
        <Sources sources={e.sources} place={e.place} />
      </div>
    </li>
  );
}

function Timeline({ spec }: { spec: TimelineSpec }) {
  const [lane, setLane] = useState<string>("");
  const rows = layoutRows(spec);
  const laneIdx = new Map(spec.lanes.map((l, i): [string, number] => [l.id, i]));
  return (
    <div className="nt">
      {spec.lanes.length >= 2 && (
        <div className="nt-lanes" role="group" aria-label="Show one thread">
          {spec.lanes.map((l, i) => (
            <button key={l.id} type="button" className={`nt-chip l${i}`} aria-pressed={lane === l.id} onClick={() => setLane(lane === l.id ? "" : l.id)}>
              {l.label}
            </button>
          ))}
        </div>
      )}
      <ol className="nt-list">
        {rows.map((r) => {
          if (r.kind === "gap")
            return (
              <li key={r.key} className={`nt-row nt-gap${r.compressed ? " is-compressed" : ""}`} style={{ height: r.px }}>
                <div className="nt-date" />
                <div className="nt-spine" aria-hidden="true" />
                <div className="nt-gaplabel">{r.label && <span>· {r.label} ·</span>}</div>
              </li>
            );
          if (r.kind === "now")
            return (
              <li key={r.key} className={`nt-row nt-now${r.first ? " is-first" : ""}${r.last ? " is-last" : ""}`}>
                <div className="nt-date">
                  <b>{dateParts(r.date).day}</b>
                </div>
                <div className="nt-spine" aria-hidden="true">
                  <span className="nt-dot nt-dot-now" />
                </div>
                <div className="nt-card">
                  <p className="nt-title">Now</p>
                </div>
              </li>
            );
          const li = laneIdx.get(r.event.lane) ?? -1;
          return <EventRow key={r.key} row={r} laneIndex={li} laneLabel={li >= 0 ? spec.lanes[li].label : ""} dim={lane !== "" && r.event.lane !== lane} />;
        })}
      </ol>
    </div>
  );
}

export default function NativeTimeline({ src, preview, title, caption }: { src: string; preview: string; title: string; caption: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [go, setGo] = useState(false);
  const [spec, setSpec] = useState<TimelineSpec | null>(null);
  const [failed, setFailed] = useState(false);

  // Fetch when the figure nears the viewport (the spec is small, but most figures are never reached).
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setGo(true);
      return;
    }
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        setGo(true);
        io.disconnect();
      }
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!go) return;
    let dead = false;
    fetch(src)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j) => {
        const s = parseTimeline(j);
        if (dead) return;
        if (s) setSpec(s);
        else setFailed(true);
      })
      .catch(() => !dead && setFailed(true));
    return () => {
      dead = true;
    };
  }, [go, src]);

  const still = preview ? <img className="nt-still" src={preview} alt={title || caption || "Timeline"} loading="lazy" /> : null;
  return (
    <div className="nt-host" ref={host}>
      {spec ? <Timeline spec={spec} /> : failed ? still : <div className="nt-wait">{still}</div>}
    </div>
  );
}
