import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActorFlag, ordinal, rankText, ScaleBar } from "@/components/actors/ActorParts";
import Crumbs, { ACTORS_CRUMB, INTEL_CRUMB } from "@/components/Crumbs";
import { Anchor, Overflow, Section } from "@/components/dossier/parts";
import { ActorDevelopments, ActorOnRecord, InvolvedIn, RelatedActors } from "@/components/entities/EntityLinks";
import PulseTile from "@/components/PulseTile";
import { actor, actorIds, CREDIT_SOURCE_ORDER, fieldOf, fmt, GROUPS, type Actor, type Field, type GroupId } from "@/lib/actors";
import { dayLabel } from "@/lib/dossier-view";
import { actorContext } from "@/lib/entities";
import { countryName } from "@/lib/flags";
import { latestSnapshot } from "@/lib/intel";
import { toWallPulse } from "@/lib/pulse-wall";

import "@/app/geopolitics/geopolitics.css";
import "../../theaters/theaters.css";

type Params = { iso: string };

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export async function generateStaticParams(): Promise<Params[]> {
  return (await actorIds()).map((iso) => ({ iso }));
}

const val = (a: Actor, id: string) => fieldOf(a, id);
const f1 = (f: Field | null) => (f ? fmt(f.value, f.unit) : "");

/** The page's claim, from the ranks it actually has: economy and military first. */
function claimOf(a: Actor): string {
  const h = (id: string) => a.headline.find((x) => x.id === id);
  const gdp = h("gdp");
  const mil = h("milex");
  const parts = [
    gdp?.rank ? `${ordinal(gdp.rank)} largest economy` : "",
    mil?.rank ? `${ordinal(mil.rank)} in military spending` : "",
  ].filter(Boolean);
  return parts.length ? `${a.name}: ${parts.join(", ")}` : `${a.name}: what it is, what it produces, who leads it`;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const a = await actor(params.iso);
  if (!a) return /^[A-Z]{2}$/.test(params.iso) ? { title: countryName(params.iso), description: `Where ${countryName(params.iso)} appears: theaters, statements and developments.` } : { title: "Actor" };
  return { title: `${a.name}: power profile`, description: claimOf(a), alternates: { canonical: `/intel/actors/${a.iso2}`, types: { "application/json": `/api/v1/actors/${a.iso2}` } } };
}

const SHOWN = 5;

function FieldList({ fields, title }: { fields: Field[]; title: string }) {
  const rows = (list: Field[]) => (
    <ul className="ac-fields">
      {list.map((f) => (
        <li key={f.id} className="ac-field">
          <span className="ac-field-k">{f.label}</span>
          <span className="ac-field-v">
            {fmt(f.value, f.unit)}
            <span className="ac-field-y">{f.year}</span>
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <>
      {rows(fields.slice(0, SHOWN))}
      {fields.length > SHOWN && (
        <Overflow label={title} trigger={`All ${fields.length} figures`}>
          {rows(fields)}
        </Overflow>
      )}
    </>
  );
}

/** Production against consumption per fuel, every bar on ONE scale (the largest value shown). */
function FuelBars({ a }: { a: Actor }) {
  const fuels = ["oil", "gas", "coal"].map((k) => ({ k, prod: val(a, `${k}_prod`), cons: val(a, `${k}_cons`) })).filter((x) => x.prod || x.cons);
  if (fuels.length === 0) return null;
  const max = Math.max(...fuels.flatMap((x) => [x.prod?.value ?? 0, x.cons?.value ?? 0]));
  return (
    <div>
      {fuels.map(({ k, prod, cons }) => (
        <div key={k} className="ac-fuel">
          <span className="ac-fuel-k">{k[0].toUpperCase() + k.slice(1)}</span>
          {[["made", prod], ["used", cons]].map(([lab, f]) => {
            const field = f as Field | null;
            return (
              <FuelRow key={lab as string} lab={lab as string} f={field} max={max} name={`${a.name} ${k} ${lab}`} />
            );
          })}
        </div>
      ))}
    </div>
  );
}

function FuelRow({ lab, f, max, name }: { lab: string; f: Field | null; max: number; name: string }) {
  return (
    <>
      {f ? <ScaleBar value={f.value} max={max} label={`${name}: ${fmt(f.value, f.unit)}`} /> : <span className="ac-none">no figure</span>}
      <span className="ac-fuel-v">
        <span className="ac-fuel-lab">{lab} </span>
        {f ? fmt(f.value, f.unit) : ""}
      </span>
    </>
  );
}

const TITLE: Record<GroupId, (a: Actor) => string> = {
  people: (a) => {
    const p = val(a, "population");
    const u = val(a, "urban_pct");
    return p ? `${f1(p)} people${u ? `, ${Math.round(u.value)}% in cities` : ""}` : "People";
  },
  economy: (a) => {
    const g = val(a, "gdp");
    const pc = val(a, "gdp_pc");
    return g ? `A ${f1(g)} economy${pc ? `, ${f1(pc)} per person` : ""}` : "Economy";
  },
  trade: (a) => {
    const fx = val(a, "fuel_exports_pct");
    const ex = val(a, "exports_pct");
    return fx ? `Fuels are ${Math.round(fx.value)}% of goods exports` : ex ? `Exports are ${Math.round(ex.value)}% of GDP` : "Trade";
  },
  energy: (a) => {
    const p = val(a, "energy_production");
    const s = a.energy_role.surplus;
    return p ? `Fossil fuel output of ${f1(p)}${s.length ? `, more than it uses in ${s.join(" and ")}` : ""}` : "Energy";
  },
  military: (a) => {
    const m = val(a, "milex");
    const pct = val(a, "milex_pct");
    return m ? `Spends ${f1(m)} on its military${pct ? `, ${f1(pct)} of GDP` : ""}` : "Military";
  },
};
const ANCHOR: Record<GroupId, string> = { people: "people", economy: "economy", trade: "trade", energy: "energy", military: "military" };

/** A state with no power profile yet but a place in the news: the same linked sections, without the numbers. */
async function ActorStub({ iso }: { iso: string }) {
  const ctx = await actorContext(iso);
  if (!ctx) notFound();
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[INTEL_CRUMB, ACTORS_CRUMB]} />
      <p className="th-kicker">
        <span>
          <ActorFlag iso2={iso} name={ctx.name} /> {ctx.name}
        </span>
      </p>
      <h1 className="th-claim">{ctx.name}: where it appears in the desk&apos;s reporting</h1>
      <p className="th-note">There is no power profile for {ctx.name} yet (economy, energy, military). Everything below comes from the theaters, statements and daily reports that name it.</p>
      <InvolvedIn name={ctx.name} theaters={ctx.theaters} />
      <ActorOnRecord name={ctx.name} said={ctx.said} about={ctx.saidAbout} />
      <ActorDevelopments name={ctx.name} items={ctx.developments} />
      <RelatedActors name={ctx.name} related={ctx.related} />
    </div>
  );
}

export default async function ActorPage({ params }: { params: Params }) {
  const a = await actor(params.iso);
  if (!a) {
    if (!/^[A-Z]{2}$/.test(params.iso)) notFound();
    return <ActorStub iso={params.iso} />;
  }
  const ctx = await actorContext(a.iso2);
  const snap = await latestSnapshot();
  const lookup = new Map((snap?.situations ?? []).flatMap((s) => s.pulses.map((p) => [p.id, toWallPulse(p, s.title)] as const)));
  const pulses = a.involved.pulses.map((p) => lookup.get(p.id)).filter((p): p is NonNullable<typeof p> => !!p);
  const { head_of_state: hos, head_of_government: hog, nuclear: nuke } = a.leadership;
  const credits = [...a.credits].sort((x, y) => CREDIT_SOURCE_ORDER.indexOf(x.source) - CREDIT_SOURCE_ORDER.indexOf(y.source));
  const said = a.statements;
  const sayText = (s: Actor["statements"][number]) => (
    <li key={s.id}>
      <span className="ac-said-who">
        {s.speaker}
        {s.role && `, ${s.role}`} · {s.date && dayLabel(s.date)}
      </span>
      {s.signal && s.signal !== "other" && <span className="ac-said-sig">{s.signal.replace(/_/g, " ")}</span>}
      <br />
      {s.is_quote ? <q>{s.text}</q> : s.text}
      {s.source_url && (
        <>
          {" "}
          <Anchor url={s.source_url}>source</Anchor>
        </>
      )}
    </li>
  );
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[INTEL_CRUMB, ACTORS_CRUMB]} />
      <p className="th-kicker">
        <span>
          <ActorFlag iso2={a.iso2} name={a.name} /> {a.name}
        </span>
        {a.region && <span className="th-domain">{a.region}</span>}
      </p>
      <h1 className="th-claim">{claimOf(a)}</h1>

      <div className="th-meta" role="group" aria-label="Leadership">
        {hos && (
          <span>
            <span className="th-k">Head of state</span> {hos.name}
          </span>
        )}
        {hog && (!hos || hog.name !== hos.name) && (
          <span>
            <span className="th-k">Head of government</span> {hog.name}
          </span>
        )}
        {a.capital && (
          <span>
            <span className="th-k">Capital</span> {a.capital}
          </span>
        )}
        {nuke && (
          <span className="ac-nuke" title={`Estimate, Federation of American Scientists ${nuke.year}`}>
            <span className="th-k">Nuclear</span> ~{nuke.stockpile.toLocaleString("en-US")} warheads
          </span>
        )}
      </div>

      {a.headline.length > 0 && (
        <div className="ac-head" role="group" aria-label="Headline numbers">
          {a.headline.map((f) => (
            <div key={f.id} className="ac-tile">
              <span className="ac-tile-k">{f.id === "energy_production" ? "Fossil fuel output" : f.label}</span>
              <span className="ac-tile-v">{fmt(f.value, f.unit)}</span>
              <span className="ac-tile-r">
                {rankText(f)} {f.rank && f.of ? "in the world" : ""} · {f.year}
              </span>
              {f.percentile !== undefined && <ScaleBar value={f.percentile} max={100} label={`Ahead of ${f.percentile}% of states`} />}
            </div>
          ))}
        </div>
      )}
      <p className="th-note">Bars show the share of states this actor is ahead of. Rank is among states, each at its latest year.</p>

      {ctx && <InvolvedIn name={a.name} theaters={ctx.theaters} />}
      {ctx && ctx.said.length > 0 && <ActorOnRecord name={a.name} said={ctx.said} about={ctx.saidAbout} />}
      {ctx && <ActorDevelopments name={a.name} items={ctx.developments} />}

      {GROUPS.map((g) =>
        a.groups[g].length === 0 ? null : (
          <Section key={g} id={ANCHOR[g]} title={TITLE[g](a)}>
            {g === "energy" && <FuelBars a={a} />}
            <FieldList fields={a.groups[g].filter((f) => !(g === "energy" && /_(prod|cons)$/.test(f.id)))} title={g[0].toUpperCase() + g.slice(1)} />
          </Section>
        ),
      )}

      {said.length > 0 && !(ctx && ctx.said.length > 0) && (
        <Section id="said" title={`What ${a.name}'s leaders said lately`} lead={`${said.length} statement${said.length === 1 ? "" : "s"} on record, newest first`}>
          <ul className="ac-said">{said.slice(0, 3).map(sayText)}</ul>
          {said.length > 3 && (
            <Overflow label={`${a.name}: statements on record`} trigger={`${said.length - 3} earlier`} wide>
              <ul className="ac-said">{said.slice(3).map(sayText)}</ul>
            </Overflow>
          )}
        </Section>
      )}

      {pulses.length > 0 && (
        <Section id="involved" title={`Pulses involving ${a.name}`} lead={<Link href="/pulses" className="xt">Every Pulse →</Link>}>
          <div className="pt-grid">
            {pulses.slice(0, SHOWN).map((p) => (
              <PulseTile key={p.id} pulse={p} size="s" anchor={false} />
            ))}
          </div>
        </Section>
      )}

      {ctx && <RelatedActors name={a.name} related={ctx.related} />}

      <Section id="credits" title="Where these numbers come from">
        <ul className="ac-credits">
          {credits.map((c) => (
            <li key={c.source}>
              <Anchor url={c.url}>{c.name}</Anchor> · {c.licence}
              {c.years && ` · ${c.years}`}
            </li>
          ))}
        </ul>
      </Section>
      <p className="th-built">
        {hos || hog ? `Leaders as of ${a.leadership.as_of || a.data_as_of}. ` : ""}Figures fetched {a.data_as_of}; each shows its own year.
      </p>
    </div>
  );
}
