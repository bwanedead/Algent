import { RELATION_KINDS } from "@/components/IntelViz";
import Popover from "@/components/Popover";
import { SourceLink } from "@/components/DailyVisuals";
import type { Actor, Relation, Statement } from "@/lib/dossier";
import { byWeight, dayLabel } from "@/lib/dossier-view";
import { kindOf, layoutNetwork, NET_H, NET_W, type RelationKind } from "@/lib/dossier-network";

import { Overflow, Section } from "./parts";

// "Who is doing what to whom": the actors as nodes (area = mentions), the relations as arrows (colour =
// kind, weight = how often reported). Hand-written SVG, laid out at build time. The picture is only
// legible on a wide screen; under 640px the same relations read as a ranked list instead (CSS swaps
// them), and the full table is always one popover away.

const verb = (k: RelationKind) => RELATION_KINDS[k].toLowerCase();

// A sentence needs a verb, not a category label: "Russia other Poland" read as nonsense.
const SENTENCE_VERB: Record<RelationKind, string> = {
  strikes: "strikes", sabotage: "sabotages", coerces: "coerces", sanctions: "sanctions",
  supports: "supports", negotiates: "negotiates with", deters: "deters", other: "acts against",
};

function RelationRow({ r }: { r: Relation }) {
  const k = kindOf(r.kind);
  return (
    <li className="th-rel">
      <span className="th-rel-line">
        <b>{r.source}</b> <span className={`th-rel-kind intel-k-${k}`}>{verb(k)}</span> <b>{r.target}</b>
        <span className="th-rel-n" title={`Reported ${r.count} time${r.count === 1 ? "" : "s"}`}>
          ×{r.count}
        </span>
        {r.last_date && <span className="th-rel-last">{dayLabel(r.last_date)}</span>}
      </span>
      {r.note && <span className="th-rel-note">{r.note}</span>}
    </li>
  );
}

function RelationTable({ relations, actors }: { relations: Relation[]; actors: Actor[] }) {
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">Every relation</p>
      <div className="th-tbl-wrap">
      <table className="th-tbl">
        <thead>
          <tr>
            <th>Who</th>
            <th>Does what</th>
            <th>To whom</th>
            <th className="th-r">Times</th>
            <th>Last</th>
          </tr>
        </thead>
        <tbody>
          {relations.map((r, i) => {
            const k = kindOf(r.kind);
            return (
              <tr key={i} title={r.note || undefined}>
                <td>{r.source}</td>
                <td className={`intel-k-${k}`}>{verb(k)}</td>
                <td>{r.target}</td>
                <td className="th-r">{r.count}</td>
                <td>{r.last_date ? dayLabel(r.last_date) : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      {actors.length > 0 && (
        <>
          <p className="geo-pd-title">Actors by mentions</p>
          <ul className="geo-plain">
            {[...actors]
              .sort((a, b) => b.mentions - a.mentions || a.name.localeCompare(b.name))
              .map((a) => (
                <li key={a.name}>
                  {a.name} <span className="geo-muted">· {a.mentions} mention{a.mentions === 1 ? "" : "s"}{a.first ? ` · since ${dayLabel(a.first)}` : ""}</span>
                </li>
              ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Statements({ items }: { items: Statement[] }) {
  return (
    <div>
      {items.map((s, i) => {
        const cap = (
          <figcaption className="geo-quote-cap">
            <span className="geo-strong">{s.who || "Unattributed"}</span>
            {s.role && <span className="geo-muted">, {s.role}</span>}
            {s.when && <span className="geo-micro"> · {dayLabel(s.when)}</span>}
            {s.source && (
              <>
                {" "}
                <SourceLink url={s.source} />
              </>
            )}
          </figcaption>
        );
        return s.quote ? (
          <figure key={i} className="geo-quote">
            <blockquote>
              <p>“{s.said}”</p>
            </blockquote>
            {cap}
          </figure>
        ) : (
          <figure key={i} className="geo-quote geo-quote-para">
            <p>
              <span className="geo-strong">{s.who || "A source"}</span> said that {s.said}
            </p>
            {cap}
          </figure>
        );
      })}
    </div>
  );
}

export default function ActorNetwork({ actors, relations, statements }: { actors: Actor[]; relations: Relation[]; statements: Statement[] }) {
  if (relations.length === 0 && actors.length === 0) return null;
  const ranked = [...relations].sort(byWeight);
  const net = layoutNetwork(actors, relations);
  const used = Array.from(new Set(net.edges.map((e) => e.kind)));
  const top = ranked[0];
  const lead = top
    ? `${top.source} ${SENTENCE_VERB[kindOf(top.kind)] ?? "→"} ${top.target} is the most-reported line (${top.count} report${top.count === 1 ? "" : "s"}${top.last_date ? `, last ${dayLabel(top.last_date)}` : ""}).`
    : `${actors.length} actor${actors.length === 1 ? "" : "s"} in play; no relations recorded yet.`;
  const topActors = [...actors].sort((a, b) => b.mentions - a.mentions).slice(0, 5);

  return (
    <Section id="actors" title="Who is doing what to whom" lead={lead}>
      {net.nodes.length >= 2 ? (
        <figure className="th-net">
          <svg viewBox={`0 0 ${NET_W} ${NET_H}`} className="th-net-svg" role="img" aria-label={`Network of ${net.nodes.length} actors and ${net.edges.length} relations. The same relations are listed in the table.`}>
            <defs>
              {used.map((k) => (
                <marker key={k} id={`th-arrow-${k}`} viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto" className={`intel-k-${k}`}>
                  <path d="M0,1 L9,5 L0,9 z" fill="currentColor" />
                </marker>
              ))}
            </defs>
            {net.edges.map((e, i) => (
              <path key={i} d={e.d} fill="none" strokeWidth={e.width} className={`th-edge intel-k-${e.kind}`} markerEnd={`url(#th-arrow-${e.kind})`}>
                <title>{`${e.rel.source} ${verb(e.kind)} ${e.rel.target}: ${e.rel.count} report${e.rel.count === 1 ? "" : "s"}${e.rel.note ? `. ${e.rel.note}` : ""}`}</title>
              </path>
            ))}
            {net.nodes.map((n) => (
              <g key={n.name}>
                <title>{`${n.name}: ${n.mentions} mention${n.mentions === 1 ? "" : "s"}`}</title>
                <circle cx={n.x} cy={n.y} r={n.r} className="th-node" />
                <text x={n.lx} y={n.ly} textAnchor={n.anchor} className="th-node-label">
                  {n.label}
                </text>
              </g>
            ))}
          </svg>
          <figcaption>
            <ul className="th-legend" aria-label="Arrow colours">
              {used.map((k) => (
                <li key={k}>
                  <svg width="22" height="8" aria-hidden="true" className={`intel-k-${k}`}>
                    <line x1="0" x2="22" y1="4" y2="4" stroke="currentColor" strokeWidth="2.5" />
                  </svg>
                  {RELATION_KINDS[k]}
                </li>
              ))}
              <li className="th-legend-note">thicker line = reported more often · bigger dot = mentioned more</li>
            </ul>
          </figcaption>
        </figure>
      ) : (
        topActors.length > 0 && (
          <ul className="th-actors">
            {topActors.map((a) => (
              <li key={a.name}>
                <b>{a.name}</b> <span className="geo-muted">{a.mentions} mention{a.mentions === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
        )
      )}

      {ranked.length > 0 && (
        <ul className={net.nodes.length >= 2 ? "th-rels" : "th-rels is-solo"} aria-label="Relations, most reported first">
          {ranked.slice(0, 6).map((r, i) => (
            <RelationRow key={i} r={r} />
          ))}
        </ul>
      )}

      <p className="th-foot">
        {ranked.length > 0 && (
          <Popover label="Relations as a table" wide triggerClassName="th-link-btn" trigger={<>All {ranked.length} relation{ranked.length === 1 ? "" : "s"} as a table ›</>}>
            <RelationTable relations={ranked} actors={actors} />
          </Popover>
        )}
        {statements.length > 0 && (
          <Overflow label="What they have said" trigger={`What they have said (${statements.length})`}>
            <Statements items={statements} />
          </Overflow>
        )}
        {net.hiddenActors > 0 && net.nodes.length >= 2 && (
          <span className="th-note th-wide-only">
            The picture shows the {net.nodes.length} most-mentioned actors; {net.hiddenActors} more {net.hiddenActors === 1 ? "is" : "are"} in the table.
          </span>
        )}
      </p>
    </Section>
  );
}
