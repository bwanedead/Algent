import Crumbs, { INTEL_CRUMB, THEATERS_CRUMB } from "@/components/Crumbs";
import { CoverSpark } from "@/components/DailyVisuals";
import LinkedText from "@/components/entities/LinkedText";
import Popover from "@/components/Popover";
import { headlineOf, isCut } from "@/lib/daily";
import type { Dossier } from "@/lib/dossier";
import { DIRECTION, dayLabel, escalationShift, isoDay, splitPrimer } from "@/lib/dossier-view";
import { COVERAGE_DISPLAY } from "@/lib/intel";

import LiveNowStrip from "@/components/live/LiveNowStrip";
import Term from "@/components/Term";

import { EscalationTrack } from "./EscalationTrack";
import { Anchor, Section } from "./parts";

// Screen one, top half: what the theater is (a small label), where it stands (the bottom line as the
// page's claim), the numbers that frame it (a meta strip) and how it got to its direction (the
// escalation trajectory). The Pulses and the map sit beside each other right below (page.tsx).

export function DossierTop({ d }: { d: Dossier }) {
  const cur = d.current;
  const claim = cur ? headlineOf(cur.headline, cur.bottom_line, 160) : d.name;
  const shift = escalationShift(d.escalation_history);
  const dir = DIRECTION[cur?.direction ?? shift?.direction ?? "unclear"];
  const moving = (cur?.direction ?? shift?.direction) === "rising" || (cur?.direction ?? shift?.direction) === "easing";
  const cov = COVERAGE_DISPLAY[cur?.coverage ?? "steady"];
  const asOf = cur?.date ? dayLabel(isoDay(cur.date) || cur.date) : "";
  return (
    <header className="th-head">
      <Crumbs trail={[INTEL_CRUMB, THEATERS_CRUMB]} />
      <p className="th-kicker">
        <span>{d.name}</span>
        {d.domain && <span className="th-domain">{d.domain}</span>}
      </p>
      <h1 className="th-claim">{claim}</h1>
      {cur && isCut(cur.bottom_line, claim) && (
        <Popover label={`Full assessment: ${d.name}`} triggerClassName="th-link-btn xt" trigger={<>Full assessment ›</>}>
          <div className="geo-pd">
            <p className="geo-pd-title">{d.name}</p>
            <p className="geo-pd-text">{cur.bottom_line}</p>
          </div>
        </Popover>
      )}
      {cur && (asOf || cur.source) && (
        <p className="th-asof">
          {asOf && <>As of {asOf}</>}
          {cur.source && (
            <>
              {asOf && " · "}
              {cur.url ? <Anchor url={cur.url}>{cur.source}</Anchor> : cur.source}
            </>
          )}
        </p>
      )}

      <LiveNowStrip scope={d.theater_id} bbox={d.map?.bbox} />

      <div className="th-meta" role="group" aria-label="Theater at a glance">
        {d.first_seen && (
          <span>
            <span className="th-k">Tracked since</span> {dayLabel(isoDay(d.first_seen) || d.first_seen)}
          </span>
        )}
        {d.days_covered > 0 && (
          <span>
            <span className="th-k">Reports</span> {d.days_covered}
          </span>
        )}
        <span className="th-cov" title="How much of the world's headlines are about this theater">
          <span className="th-k"><Term id="coverage">Coverage</Term></span> <span aria-hidden="true">{cov.glyph}</span> {cov.label}
          {d.coverage_series.length > 1 && <CoverSpark series={d.coverage_series} coverage={cur?.coverage ?? "steady"} name={d.name} />}
        </span>
        <span className={moving ? "th-dir is-moving" : "th-dir"} title="Is the situation itself getting worse, steadier or easing">
          <span className="th-k"><Term id="direction" label="escalation">Escalation</Term></span> <span aria-hidden="true">{dir.glyph}</span> {dir.word}
          {cur && cur.pace !== "flat" && <> · {cur.pace}</>}
          {shift && !shift.first && (
            <span className="th-since">
              {" "}
              since {dayLabel(isoDay(shift.since) || shift.since)}
              {shift.was && <> (was {DIRECTION[shift.was].glyph} {DIRECTION[shift.was].word})</>}
            </span>
          )}
        </span>
      </div>

      <EscalationTrack history={d.escalation_history} name={d.name} />
    </header>
  );
}

/** The newcomer's on-ramp: visible and compact; the long tail waits in a popover. Hidden when there is no primer. */
export function DossierPrimer({ primer }: { primer: Dossier["primer"] }) {
  if (!primer) return null;
  const { lead, rest } = splitPrimer(primer.text);
  return (
    <Section id="background" title="Background in 60 seconds" aside={primer.built_at ? <span className="th-key">written {dayLabel(isoDay(primer.built_at) || primer.built_at)}</span> : undefined}>
      <div className="th-primer">
        {lead.map((p, i) => (
          <p key={i}><LinkedText text={p} /></p>
        ))}
      </div>
      {rest && (
        <Popover label="Background, in full" wide triggerClassName="th-link-btn xt" trigger={<>Read the rest ›</>}>
          <div className="geo-pd">
            {primer.text
              .split(/\n\s*\n/)
              .map((p) => p.trim())
              .filter(Boolean)
              .map((p, i) => (
                <p key={i} className="geo-pd-text">
                  <LinkedText text={p} />
                </p>
              ))}
          </div>
        </Popover>
      )}
    </Section>
  );
}
