import Link from "next/link";

import { countryName } from "@/lib/flags";
import { CHANGE_WORD, NIGHT_WORD, pct, provText, type Provenance, type SatSite } from "@/lib/satellite-shared";

import BeforeAfter from "./BeforeAfter";

import "./satellite.css";

/** The info hover: how the number was made and how much of our own history it rests on (the `title` is the tooltip, `aria-label` the screen-reader text). */
export function Info({ p }: { p: Partial<Provenance> }) {
  const text = provText(p);
  return <span className="sat-i" title={text} aria-label={text} role="img" tabIndex={0}>i</span>;
}

/** One watched site: its before / after pair, the machine change signal and night-light verdict with their provenance, the reason it is watched,
 *  and links to the asset, country and theater pages where they exist. Server component (the slider is the only client part). */
export default function SiteCard({ s }: { s: SatSite }) {
  const c = s.change;
  const n = s.night;
  const flag = c?.label === "changed" ? "changed" : n?.label === "dimmer" ? "dimmer" : "";
  return (
    <li className="sat-card" id={s.id}>
      <div className="sat-head">
        <h3 className="sat-name">{s.name}</h3>
        {c && <span className={`sat-flag${flag ? ` is-${flag}` : ""}`}>{CHANGE_WORD[c.label]}<Info p={c} /></span>}
      </div>
      {s.baseline && s.latest && s.baseline.chip !== s.latest.chip ? (
        <BeforeAfter name={s.name} before={s.baseline} after={s.latest} />
      ) : (
        <p className="sat-none">{s.latest ? `One picture so far (${s.latest.date}); a second scene is needed for a comparison.` : "No usable scene yet."}</p>
      )}
      {c && (
        <dl className="sat-facts">
          <div><dt>Change score</dt><dd>{c.score === null ? "n/a" : c.score.toFixed(3)}</dd></div>
          <div><dt>Pixels changed</dt><dd>{pct(c.changed_frac)}</dd></div>
          <div><dt>Clear ground</dt><dd>{pct(c.valid_share, 0)}</dd></div>
          <div><dt>Cloud now / before</dt><dd>{s.latest ? `${s.latest.local_cloud_pct}%` : "n/a"} / {s.baseline ? `${s.baseline.local_cloud_pct}%` : "n/a"}</dd></div>
          {n && n.label && (
            <div><dt>Night light<Info p={n} /></dt><dd>{NIGHT_WORD[n.label]}{n.date ? `, ${n.date}` : ""}</dd></div>
          )}
        </dl>
      )}
      {c && <p className="sat-why">{c.reason}</p>}
      {s.why.length > 0 && <p className="sat-why">Watched: {s.why.join("; ")}{s.event_on ? `. Baseline is the clearest scene before ${s.event_on}.` : "."}</p>}
      <p className="sat-links">
        {s.links.asset && <Link href={`/intel/places/${s.links.asset}`} className="xt">Place</Link>}
        {s.links.country && <Link href={`/intel/actors/${s.links.country}`} className="xt">{countryName(s.links.country)}</Link>}
        {s.links.theater && <Link href={`/intel/theaters/${s.links.theater}`} className="xt">Theater</Link>}
        <a href={`https://www.openstreetmap.org/?mlat=${s.lat}&mlon=${s.lon}#map=14/${s.lat}/${s.lon}`} className="xt" rel="noopener noreferrer">Map</a>
      </p>
    </li>
  );
}
