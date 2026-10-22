import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";

import Crumbs, { DATA_CRUMB } from "@/components/Crumbs";
import { SourceLink } from "@/components/DailyVisuals";
import { Section } from "@/components/dossier/parts";
import { ActorLink, TheaterLink } from "@/components/entities/EntityLinks";
import BehaviourList from "@/components/maritime/BehaviourList";
import PointMap from "@/components/places/PointMap";
import { dayLabel } from "@/lib/dossier-view";
import { countryName } from "@/lib/flags";
import { capacityLabel, STATUS_LABEL, STATUS_MEANING, statusTone, TYPE_LABEL } from "@/lib/geoledger-shared";
import { imoOf, maritimeForVessel } from "@/lib/maritime";
import { placeContext } from "@/lib/places";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

type Params = { id: string };

export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const ctx = await placeContext(params.id);
  if (!ctx) return { title: "Place" };
  const { asset } = ctx;
  const country = asset.country ? countryName(asset.country) : "";
  return {
    title: `${asset.name}${country ? `, ${country}` : ""}`,
    description: `${TYPE_LABEL[asset.type]}${country ? ` in ${country}` : ""}: what has been said about it, by whom, and when.`,
    alternates: { canonical: `/intel/places/${asset.id}` },
    // A place nobody has said anything about is a catalogue entry, not a page worth indexing.
    robots: asset.events > 0 ? undefined : { index: false, follow: true },
  };
}

// A named place as an object: what it is, where, and the dated statements about its state, each with who said it. A claim is a
// party's word, never a confirmation (lib/geoledger-shared.ts keeps them apart).
export default async function PlacePage({ params }: { params: Params }) {
  const ctx = await placeContext(params.id);
  if (!ctx) notFound();
  if (ctx.asset.merged_into) permanentRedirect(`/intel/places/${ctx.asset.merged_into}`);          // a spelling joined into another place
  const { asset, history, theaters } = ctx;
  const imo = asset.type === "vessel" ? imoOf(asset) : "";
  const behaviour = imo ? await maritimeForVessel({ imo }) : []; // what Ohmega saw this ship do (AIS), beside what parties said about it
  const iso = asset.country.toUpperCase();
  const cap = capacityLabel(asset);
  const newest = [...history].reverse();
  const placed = asset.lat !== null && asset.lon !== null && asset.loc_precision !== "unplaced";
  const spread = asset.loc_precision === "exact" ? 0.25 : asset.loc_precision === "city_level" ? 0.5 : 0.8;
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[DATA_CRUMB]} />
      <p className="th-kicker">
        <span>{TYPE_LABEL[asset.type]}</span>
        {asset.status && (
          <span>
            <span aria-hidden="true" style={{ color: statusTone(asset.status) }}>● </span>
            {STATUS_LABEL[asset.status]}
          </span>
        )}
      </p>
      <h1 className="th-claim">{asset.name}</h1>
      <div className="th-meta" role="group" aria-label="The place at a glance">
        {/^[A-Z]{2}$/.test(iso) && (
          <span>
            <span className="th-k">Country</span> <ActorLink iso2={iso} name={countryName(iso)} />
          </span>
        )}
        {cap && (
          <span>
            <span className="th-k">Capacity</span> {cap}
          </span>
        )}
        {asset.aliases.length > 0 && (
          <span>
            <span className="th-k">Also written</span> {asset.aliases.slice(0, 4).join(", ")}
          </span>
        )}
      </div>

      {placed && (
        <PointMap
          lat={asset.lat as number}
          lon={asset.lon as number}
          label={`Map: ${asset.name}`}
          asset={asset}
          spread={spread}
          note={asset.loc_precision === "exact" ? "" : asset.loc_precision === "city_level" ? "Position is the town's, not the site's." : "Position is approximate."}
        />
      )}

      <Section
        id="history"
        title={history.length > 0 ? `${history.length} status ${history.length === 1 ? "report" : "reports"}, newest first` : "Nothing on record about its state"}
        lead="Each line is somebody's word: a claim by a party stays a claim until someone else reports or confirms damage."
      >
        {history.length > 0 && (
          <ul className="geo-ctx">
            {newest.map((e) => (
              <li key={e.id}>
                <span className="geo-micro geo-ctx-when">{dayLabel(e.occurred_on)}</span>
                <span>
                  <span className="geo-ctx-what">
                    <span aria-hidden="true" style={{ color: statusTone(e.status) }}>● </span>
                    <b className="geo-strong" title={STATUS_MEANING[e.status]}>{STATUS_LABEL[e.status]}</b>
                  </span>{" "}
                  <span className="geo-muted">
                    · said by {e.claimant}
                    {e.confidence === "low" ? " · low confidence" : ""}
                  </span>
                  {e.note && <span className="geo-muted"> · {e.note}</span>}
                  {e.sources.slice(0, 3).map((u) => (
                    <span key={u}>
                      {" "}
                      <SourceLink url={u} />
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {behaviour.length > 0 && (
        <Section
          id="behaviour"
          title={`${behaviour.length} behaviour ${behaviour.length === 1 ? "event" : "events"} seen by Ohmega`}
          lead="Ohmega's own analysis of this ship's AIS broadcasts, not something a party said: a pattern seen, never a finding of intent."
        >
          <BehaviourList events={behaviour} nowMs={Date.now()} />
        </Section>
      )}

      {theaters.length > 0 && (
        <Section id="theaters" title={`Appears in ${theaters.length} theater${theaters.length === 1 ? "" : "s"}`} lead="The theaters whose reports put it on the record.">
          <ul className="en-rows">
            {theaters.map((t) => (
              <li key={t.id}>
                <TheaterLink t={t} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      <p className="th-built">
        {asset.provenance === "ohmega_derived" ? "Place found by our own reading of the reports. " : ""}
        {[asset.source, asset.licence].filter(Boolean).join(", ")}
      </p>
    </div>
  );
}
