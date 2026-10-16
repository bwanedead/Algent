"use client";

// The living network (daily visual kind "network" with a `spec`; contract: backend agents/intel/network_spec.py): who backs,
// funds, arms, opposes or depends on whom. Parties are nodes laid out by a small force simulation (netLayout.ts), ties are
// lines in one of four colour families (backing, hostile, exchange, talks - the visual language's category tints) with pulses
// that run in the direction of the relation. Tap a party for its ties, or a tie for what a source says about it. When ties
// begin or end on dates the story has a scrubber (and a play button): the picture at each date shows only the ties in force.
// Reduced motion: no pulses, no autoplay; the scrubber still steps. The list of all ties under the figure is the text
// alternative and works with the keyboard. If the spec cannot load, the server-drawn still takes its place.
// Client-safe imports only. The spec is fetched in the browser from our published assets.

import { useEffect, useMemo, useRef, useState } from "react";

import IsoFlags from "@/components/IsoFlags";
import { activeOn, frameDates, layout, tiePath, VIEW_H, VIEW_W } from "@/components/netLayout";
import { dateParts } from "@/components/timelineLayout";
import { useSpec } from "@/components/useSpec";
import { NET_PHRASE, parseNetwork, type NetEdge, type NetFamily, type NetNode, type NetworkSpec } from "@/lib/visualSpecs";

import "./nativeviz.css";

const FAMILY_WORD: Record<NetFamily, string> = { backing: "Backs", hostile: "Opposes", exchange: "Trades or depends", talks: "Talks" };
const FAMILIES: NetFamily[] = ["backing", "hostile", "exchange", "talks"];
const PLAY_MS = 1700;
const calm = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const fmtDate = (iso: string) => {
  const d = dateParts(iso);
  return `${d.day} ${d.year}`;
};
const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

type Sel = { kind: "node" | "edge"; id: string } | null;

function SourceList({ edge }: { edge: NetEdge }) {
  if (edge.sources.length === 0) return null;
  return (
    <p className="nv-src">
      {edge.sources.map((s, i) =>
        s.url ? (
          <a key={i} href={s.url} className="geo-src" target="_blank" rel="noopener noreferrer nofollow">
            {s.label || hostOf(s.url)} ↗
          </a>
        ) : (
          <span key={i} className="geo-micro">
            {s.label}
          </span>
        ),
      )}
    </p>
  );
}

function Network({ spec }: { spec: NetworkSpec }) {
  const pos = useMemo(() => layout(spec.nodes, spec.edges), [spec]);
  const nodes = useMemo(() => new Map(spec.nodes.map((n): [string, NetNode] => [n.id, n])), [spec]);
  const frames = useMemo(() => frameDates(spec.edges), [spec]);
  const [step, setStep] = useState(Math.max(0, frames.length - 1)); // open on the latest state of the story
  const [sel, setSel] = useState<Sel>(null);
  const [playing, setPlaying] = useState(false);
  const still = useRef(calm());
  const date = frames.length ? frames[step] : "";

  const live = useMemo(() => spec.edges.filter((e) => activeOn(e, date)), [spec, date]);
  const touched = useMemo(() => new Set(live.flatMap((e) => [e.source, e.target])), [live]);
  const changes = useMemo(
    () =>
      date
        ? spec.edges.flatMap((e) => [
            ...(e.start === date ? [{ sign: "+", e }] : []),
            ...(e.end === date ? [{ sign: "−", e }] : []),
          ])
        : [],
    [spec, date],
  );
  // Ties that share the same pair of parties are bowed apart so none hides another.
  const bows = useMemo(() => {
    const seen = new Map<string, number>();
    const out = new Map<string, number>();
    for (const e of spec.edges) {
      const key = [e.source, e.target].sort().join("|");
      const k = seen.get(key) ?? 0;
      seen.set(key, k + 1);
      out.set(e.id, k === 0 ? 0 : (k % 2 ? 1 : -1) * 16 * Math.ceil(k / 2));
    }
    return out;
  }, [spec]);

  useEffect(() => {
    if (!playing) return;
    const t = window.setTimeout(() => {
      if (step >= frames.length - 1) setPlaying(false);
      else setStep(step + 1);
    }, PLAY_MS);
    return () => window.clearTimeout(t);
  }, [playing, step, frames.length]);

  const play = () => {
    if (playing) return setPlaying(false);
    if (step >= frames.length - 1) setStep(0);
    setSel(null);
    setPlaying(true);
  };
  const pick = (s: Sel) => {
    setPlaying(false);
    setSel(sel && s && sel.kind === s.kind && sel.id === s.id ? null : s);
  };

  const selEdge = sel?.kind === "edge" ? spec.edges.find((e) => e.id === sel.id) : undefined;
  const selNode = sel?.kind === "node" ? nodes.get(sel.id) : undefined;
  const hot = (e: NetEdge) => (selEdge ? e.id === selEdge.id : selNode ? e.source === selNode.id || e.target === selNode.id : true);
  const used = FAMILIES.filter((f) => spec.edges.some((e) => e.family === f));
  const nodeTies = selNode ? live.filter((e) => e.source === selNode.id || e.target === selNode.id) : [];
  const label = (id: string) => nodes.get(id)?.label ?? id;
  const tieText = (e: NetEdge) => `${label(e.source)} ${NET_PHRASE[e.relation]} ${label(e.target)}`;

  return (
    <div className="nn">
      <svg className="nn-svg" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} role="img" aria-label={`Network: ${spec.title || spec.caption}. The ties are listed below the figure.`}>
        <defs>
          {FAMILIES.map((f) => (
            <marker key={f} id={`nn-m-${f}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" className={`nn-arrow nn-f-${f}`} />
            </marker>
          ))}
        </defs>
        <rect x={0} y={0} width={VIEW_W} height={VIEW_H} fill="transparent" onClick={() => setSel(null)} aria-hidden="true" />
        {live.map((e) => {
          const a = pos.get(e.source);
          const b = pos.get(e.target);
          if (!a || !b) return null;
          const { d } = tiePath(a, b, bows.get(e.id) ?? 0);
          const back = e.both ? tiePath(b, a, -(bows.get(e.id) ?? 0)).d : "";
          const w = 1 + e.strength * 0.9;
          return (
            <g key={e.id} className={`nn-tie nn-f-${e.family}${hot(e) ? "" : " is-dim"}${selEdge?.id === e.id ? " is-sel" : ""}`}>
              <path d={d} className="nn-line" strokeWidth={w} markerEnd={`url(#nn-m-${e.family})`} markerStart={e.both ? `url(#nn-m-${e.family})` : undefined} />
              <path d={d} className="nn-pulse" strokeWidth={w + 1.2} />
              {back && <path d={back} className="nn-pulse nn-pulse-back" strokeWidth={w + 1.2} />}
              <path d={d} className="nn-hit" strokeWidth={18} onClick={() => pick({ kind: "edge", id: e.id })} aria-hidden="true" />
            </g>
          );
        })}
        {spec.nodes.map((n) => {
          const p = pos.get(n.id);
          if (!p) return null;
          const right = p.x >= VIEW_W / 2;
          const on = touched.has(n.id) || !date;
          const dim = (selNode && selNode.id !== n.id && !nodeTies.some((e) => e.source === n.id || e.target === n.id)) || (selEdge && selEdge.source !== n.id && selEdge.target !== n.id);
          return (
            <g
              key={n.id}
              className={`nn-node k-${n.kind}${on ? "" : " is-off"}${dim ? " is-dim" : ""}${selNode?.id === n.id ? " is-sel" : ""}`}
              role="button"
              tabIndex={0}
              aria-label={`${n.label}${n.weight ? `, ${n.weight.toLocaleString("en")} ${spec.weightLabel}` : ""}`}
              aria-pressed={selNode?.id === n.id}
              onClick={() => pick({ kind: "node", id: n.id })}
              onKeyDown={(ev) => {
                if (ev.key === "Enter" || ev.key === " ") {
                  ev.preventDefault();
                  pick({ kind: "node", id: n.id });
                }
              }}
            >
              <circle cx={p.x} cy={p.y} r={p.r + 8} className="nn-touch" />
              <circle cx={p.x} cy={p.y} r={p.r} className="nn-dot" />
              <text x={p.x + (right ? p.r + 5 : -p.r - 5)} y={p.y + 4} textAnchor={right ? "start" : "end"} className="nn-label">
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>

      <ul className="nn-key" aria-label="Colour key">
        {used.map((f) => (
          <li key={f} className={`nn-f-${f}`}>
            <i aria-hidden="true" />
            {FAMILY_WORD[f]}
          </li>
        ))}
        {spec.weightLabel && <li className="nn-size">Size: {spec.weightLabel}</li>}
      </ul>

      {frames.length > 0 && (
        <div className="nv-bar">
          {!still.current && (
            <button type="button" className="nv-btn" onClick={play} aria-label={playing ? "Pause" : "Play through time"}>
              {playing ? "❚❚ Pause" : "▶ Play"}
            </button>
          )}
          <input
            className="nv-range"
            type="range"
            min={0}
            max={frames.length - 1}
            step={1}
            value={step}
            onChange={(e) => {
              setPlaying(false);
              setStep(Number(e.target.value));
            }}
            aria-label="Date"
            aria-valuetext={`${fmtDate(date)}, step ${step + 1} of ${frames.length}`}
          />
          <span className="nv-count">{fmtDate(date)}</span>
        </div>
      )}

      <div className="nv-detail" aria-live={playing ? "off" : "polite"}>
        {selEdge ? (
          <>
            <p className="nv-head">{tieText(selEdge)}</p>
            {selEdge.detail && <p className="nv-text">{selEdge.detail}</p>}
            {(selEdge.start || selEdge.end) && (
              <p className="nv-meta">
                {selEdge.start && `From ${fmtDate(selEdge.start)}`}
                {selEdge.start && selEdge.end && " · "}
                {selEdge.end && `Until ${fmtDate(selEdge.end)}`}
              </p>
            )}
            <SourceList edge={selEdge} />
          </>
        ) : selNode ? (
          <>
            <p className="nv-head">
              {selNode.iso && <IsoFlags codes={[selNode.iso]} />} {selNode.label}
            </p>
            {selNode.weight > 0 && (
              <p className="nv-meta">
                {selNode.weight.toLocaleString("en")} · {spec.weightLabel}
              </p>
            )}
            {nodeTies.length === 0 ? (
              <p className="nv-text">No ties at this date.</p>
            ) : (
              <ul className="nv-ties">
                {nodeTies.map((e) => (
                  <li key={e.id}>
                    <button type="button" onClick={() => pick({ kind: "edge", id: e.id })}>
                      {tieText(e)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : changes.length > 0 ? (
          <>
            <p className="nv-head">{fmtDate(date)}</p>
            <ul className="nv-ties">
              {changes.map((c, i) => (
                <li key={i}>
                  <button type="button" onClick={() => pick({ kind: "edge", id: c.e.id })}>
                    <b>{c.sign}</b> {tieText(c.e)}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="nv-hint">{spec.caption || "Tap a party or a line."}</p>
        )}
      </div>

      <details className="nv-all">
        <summary>All {spec.edges.length} ties</summary>
        <ol>
          {spec.edges.map((e) => (
            <li key={e.id} className={selEdge?.id === e.id ? "is-on" : ""}>
              <button type="button" onClick={() => pick({ kind: "edge", id: e.id })}>
                <b>{tieText(e)}</b>
                {e.start ? ` (from ${fmtDate(e.start)})` : ""}
                {e.end ? ` (until ${fmtDate(e.end)})` : ""}
                {e.detail ? `. ${e.detail}` : ""}
              </button>
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}

export default function NativeNetwork({ src, preview, title, caption }: { src: string; preview: string; title: string; caption: string }) {
  const { host, spec, failed } = useSpec(src, parseNetwork);
  const still = preview ? <img className="nv-still" src={preview} alt={title || caption || "Network"} loading="lazy" /> : null;
  return <div className="nv-host" ref={host}>{spec ? <Network spec={spec} /> : failed ? still : <div className="nv-wait">{still}</div>}</div>;
}
