"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { DailyDevelopment, TheaterMap } from "@/lib/daily";

import { layoutMap } from "./layout";
import { mapIndexBase } from "./numbering";

// THE map of the site: daily-report theaters and dossier maps both draw through this. A utilitarian
// reference map, not a styled one — pale water, light land, grey borders, dark labels with a white halo,
// rivers, reference cities, a scale bar and a locator inset, and the event marks numbered as in the
// development list. Legible in BOTH themes because the map is a light "printed" panel either way
// (colours are map-local variables in app/geopolitics/geopolitics.css, not theme tokens).
// Geometry is the backend's (geo.build_map); label PLACEMENT is done here because it depends on the real
// rendered size: the same map shows fewer labels on a phone than on a desktop, and never overlapping ones.
// Disputed/occupied areas (spec `disputed`, Natural Earth + a cited status table) are one quiet diagonal hatch
// over the land, in a hue used for nothing else on the map; the status note and its source open on tap/Enter.
// Doctrine: docs/ethos/information-ergonomics-ethos.md. Spec: docs/architecture/map-analytics-stack.md.

const DEFAULT_K = 0.7; // rendered px per viewBox unit before the browser has measured the figure (`initialK` overrides it: server render, previews)

export default function GeoMap({ map, developments, label, initialK = DEFAULT_K }: { map: TheaterMap | null; developments: DailyDevelopment[]; label?: string; initialK?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  const [k, setK] = useState(initialK);
  const [openArea, setOpenArea] = useState<number | null>(null); // index into map.disputed whose note is shown
  const hatchId = `geo-hatch-${useId().replace(/:/g, "")}`;
  useEffect(() => {
    const el = ref.current;
    if (!el || !map || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setK(Math.round((w / map.width) * 100) / 100);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);

  const base = map ? mapIndexBase(map, developments.length) : 0;
  const lay = useMemo(() => (map ? layoutMap(map, k) : null), [map, k]);
  if (!map || !lay) return null;
  const u = (px: number) => px / k; // CSS px -> viewBox units, so type stays one size however the map scales
  const marks = map.points.map((p, i) => {
    const di = p.n === null ? -1 : p.n - base;
    const dev = di >= 0 && di < developments.length ? developments[di] : null;
    return { p, num: dev ? di + 1 : p.n ?? i + 1, headline: dev ? dev.headline : p.label };
  });
  const r = u(lay.markR);
  const loc = lay.locator;
  const areas = map.disputed;
  const area = openArea !== null && openArea < areas.length ? areas[openArea] : null;
  const toggle = (i: number) => setOpenArea((cur) => (cur === i ? null : i));
  return (
    <figure className="geo-map">
      <svg ref={ref} viewBox={`0 0 ${map.width} ${map.height}`} role="img" className="geo-map-svg" style={{ ["--u" as string]: (1 / k).toFixed(3) }}
           aria-label={label ?? `Map: ${marks.length} marked place${marks.length === 1 ? "" : "s"}, numbered as in the timeline.`}>
        {areas.length > 0 && (
          <defs>
            <pattern id={hatchId} patternUnits="userSpaceOnUse" width={u(6)} height={u(6)} patternTransform="rotate(45)">
              <line x1={0} y1={0} x2={0} y2={u(6)} className="geo-hatch-line" strokeWidth={u(1.2)} />
            </pattern>
          </defs>
        )}
        <rect width={map.width} height={map.height} className="geo-map-sea" />
        {map.countries.map((c, i) => (
          <path key={i} d={c.d} className="geo-map-land">
            {c.name && <title>{c.name}</title>}
          </path>
        ))}
        {areas.map((a, i) => (
          <path key={`x${i}`} d={a.d} fill={`url(#${hatchId})`} className={openArea === i ? "geo-disputed is-open" : "geo-disputed"} role="button" tabIndex={0}
                aria-label={`${a.name}: disputed or occupied territory. Press for the status note.`}
                onClick={() => toggle(i)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(i); } }}>
            <title>{`${a.name} — ${a.note}`}</title>
          </path>
        ))}
        {map.lakes.map((d, i) => <path key={`l${i}`} d={d} className="geo-map-lake" />)}
        {map.rivers.map((d, i) => <path key={`r${i}`} d={d} className="geo-map-river" />)}

        {lay.countryLabels.map((l, i) => (
          <text key={`c${i}`} x={l.x} y={l.y} textAnchor="middle" dominantBaseline="central" fontSize={u(l.px)} className="geo-map-country">
            {l.text}
          </text>
        ))}

        {lay.disputedLabels.map((l, i) => (
          <text key={`d${i}`} x={l.x} y={l.y} textAnchor={l.anchor} dominantBaseline="central" fontSize={u(l.px)} className="geo-map-disputed">
            {l.text}
          </text>
        ))}

        {lay.cities.map((c, i) => (
          <g key={`t${i}`} className={c.capital ? "geo-city is-cap" : "geo-city"}>
            <circle cx={c.x} cy={c.y} r={u(c.capital ? 3 : 2.2)} />
            {c.label && (
              <text x={c.label.x} y={c.label.y} textAnchor={c.label.anchor} dominantBaseline="central" fontSize={u(lay.cityPx)}>
                {c.name}
              </text>
            )}
          </g>
        ))}

        {lay.annotations.map((a, i) => (
          <g key={`a${i}`} className="geo-note">
            <line x1={a.x} y1={a.y} x2={a.leader.x} y2={a.leader.y} strokeWidth={u(1.2)} />
            <rect x={a.box.x} y={a.box.y} width={a.box.w} height={a.box.h} rx={u(2)} strokeWidth={u(1)} />
            {a.rows.map((row, j) => (
              <text key={j} x={a.box.x + u(6)} y={a.box.y + u(6) + u(lay.notePx) * (j + 0.5) * 1.25 + (j > 0 ? u(1) : 0)} dominantBaseline="central"
                    fontSize={u(lay.notePx)} className={j === 0 ? "geo-note-title" : undefined}>
                {row}
              </text>
            ))}
            <path d={`M${a.x} ${a.y - u(6)}L${a.x + u(6)} ${a.y}L${a.x} ${a.y + u(6)}L${a.x - u(6)} ${a.y}Z`} strokeWidth={u(1.4)} />
          </g>
        ))}

        {marks.map(({ p, num, headline }, i) => {
          const pl = lay.placeLabels[i];
          return (
            <g key={i} transform={`translate(${lay.markPos[i].x.toFixed(1)} ${lay.markPos[i].y.toFixed(1)})`} className={p.verification === "researched" ? "geo-pt geo-pt-solid" : "geo-pt geo-pt-hollow"}>
              <title>{[headline, p.date, p.verification === "researched" ? "researched" : "reported"].filter(Boolean).join(" · ")}</title>
              <circle r={r} strokeWidth={u(1.6)} />
              <text textAnchor="middle" dominantBaseline="central" fontSize={u(lay.markPx)} className="geo-pt-num">
                {num}
              </text>
              {pl && (
                <text x={pl.x - lay.markPos[i].x} y={pl.y - lay.markPos[i].y} textAnchor={pl.anchor} dominantBaseline="central" fontSize={u(lay.cityPx)} className="geo-map-place">
                  {pl.text}
                </text>
              )}
            </g>
          );
        })}

        {map.scale && (
          <g className="geo-scale" transform={`translate(${u(12)} ${map.height - u(14)})`}>
            <rect x={-u(5)} y={-u(17)} width={map.scale.px + u(10)} height={u(31)} className="geo-scale-bg" />
            <text x={0} y={-u(8)} fontSize={u(10.5)} dominantBaseline="central">{map.scale.label}</text>
            <path d={`M0 ${u(2)}V${u(8)}H${map.scale.px}V${u(2)}`} strokeWidth={u(1.6)} />
          </g>
        )}

        {map.locator && loc && (
          <g className="geo-locator" transform={`translate(${map.width - loc.w - u(8)} ${u(8)})`}>
            <rect width={loc.w} height={loc.h} className="geo-locator-bg" strokeWidth={u(1)} />
            <g transform={`scale(${loc.w / map.locator.width})`}>
              <path d={map.locator.d} className="geo-locator-land" />
              <rect x={map.locator.rect.x} y={map.locator.rect.y} width={map.locator.rect.w} height={map.locator.rect.h} className="geo-locator-box" />
            </g>
          </g>
        )}
      </svg>
      {areas.length > 0 && (
        <div className="geo-map-legend">
          <p className="geo-micro geo-legend-line">
            <span className="geo-hatch-swatch" aria-hidden="true" />
            Hatched: disputed or occupied territory, as of the dataset; see note.
          </p>
          <p className="geo-legend-note" aria-live="polite">
            {area ? (
              <>
                <strong className="geo-strong">{area.name}</strong> — {area.note}{" "}
                {area.source && <a href={area.source} target="_blank" rel="noopener noreferrer">Source</a>}{" "}
                <button type="button" className="geo-link-btn geo-legend-close" onClick={() => setOpenArea(null)}>Close</button>
              </>
            ) : (
              <span className="geo-muted">Tap a hatched area for its status and source.</span>
            )}
          </p>
        </div>
      )}
      {map.credit && <figcaption className="geo-micro geo-map-credit">{map.credit}</figcaption>}
    </figure>
  );
}
