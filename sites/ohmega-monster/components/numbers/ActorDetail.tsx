import Link from "next/link";

import { ActorFlag, ScaleBar } from "@/components/actors/ActorParts";
import { fmt, type Unit } from "@/lib/actors";
import type { ActorMetric, NumbersActor, RankedLine, RankedTrade } from "@/lib/daily";

import Sparkline from "./Sparkline";
import "./numbers.css";

// An actor's popover: who leads it, then its structure in annual statistics (size, energy, trade, balance sheet,
// military) — every row a figure with its YEAR, a ten-year trend line and its world rank — and its ranked trade.
// These are annual statistics, not live data; the footer names each source used.

/** Display of one metric; a negative share is a surplus/deficit and keeps its sign. */
export const showMetric = (m: ActorMetric): string => fmt(m.value, (m.unit || "number") as Unit);

const GROUPS: { title: string; ids: string[] }[] = [
  { title: "Size and people", ids: ["gdp", "gdp_pc", "population", "gdp_growth"] },
  { title: "Energy", ids: ["energy_production", "energy_use", "energy_import_pct"] },
  { title: "Trade", ids: ["exports_pct", "imports_pct", "exports_usd", "imports_usd", "fuel_exports_pct"] },
  { title: "Balance sheet", ids: ["gov_debt_imf", "fiscal_balance_imf", "current_account_imf", "reserves_usd", "reserves_months", "ext_debt_usd", "ext_debt_gni", "policy_rate"] },
  { title: "Military", ids: ["milex", "milex_pct", "armed_forces"] },
];
const FUELS: [string, string, string][] = [["Oil", "oil_prod", "oil_cons"], ["Gas", "gas_prod", "gas_cons"], ["Coal", "coal_prod", "coal_cons"]];
const SOURCE: Record<string, string> = {
  wb: "World Bank WDI (military: SIPRI)",
  owid: "Our World in Data / Energy Institute",
  imf: "IMF World Economic Outlook",
  bis: "Bank for International Settlements",
};

const rankText = (m: ActorMetric): string => (m.rank !== null && m.of !== null ? `#${m.rank} of ${m.of}` : "");

function Row({ id, m, asOfYear }: { id: string; m: ActorMetric; asOfYear: number }) {
  const est = m.source === "imf" && m.year >= asOfYear;
  const text =
    id === "energy_import_pct"
      ? m.value < 0
        ? `net exporter: ${Math.abs(m.value).toFixed(0)}% of its use`
        : `imports ${m.value.toFixed(0)}% of its use`
      : showMetric(m);
  return (
    <li>
      <span className="geo-muted">{m.label}</span>
      <span>
        <b className="geo-strong">{text}</b> <span className="geo-muted">({m.year}{est ? " est." : ""})</span>
      </span>
      <span className="num-mspark">
        {m.trend.length >= 3 && <Sparkline values={m.trend.map((p) => p[1])} label={`${m.label}, ${m.trend[0][0]} to ${m.trend[m.trend.length - 1][0]}`} />}
      </span>
      <span className="geo-muted">{rankText(m)}</span>
    </li>
  );
}

function FuelRows({ metrics }: { metrics: Record<string, ActorMetric> }) {
  return (
    <>
      {FUELS.filter(([, p, c]) => metrics[p] || metrics[c]).map(([name, p, c]) => {
        const made = metrics[p];
        const used = metrics[c];
        return (
          <li key={name}>
            <span className="geo-muted">{name}</span>
            <span>
              {made ? <b className="geo-strong">{showMetric(made)}</b> : "—"} made · {used ? <b className="geo-strong">{showMetric(used)}</b> : "—"} used
            </span>
            <span className="num-mspark" />
            <span className="geo-muted">{(made ?? used)?.year}</span>
          </li>
        );
      })}
    </>
  );
}

function RankedList({ title, lines, flags }: { title: string; lines: RankedLine[]; flags: boolean }) {
  if (lines.length === 0) return null;
  const max = Math.max(...lines.map((l) => l.share));
  return (
    <div className="num-ranked">
      <p className="geo-micro">{title}</p>
      <ul>
        {lines.map((l, i) => (
          <li key={`${l.name}-${i}`}>
            <span className="num-rname">
              <span className="geo-muted">{i + 1}</span> {flags && l.iso2 ? <ActorFlag iso2={l.iso2} name={l.name} /> : null} {l.name}
            </span>
            <ScaleBar value={l.share} max={max} label={`${l.name}: ${l.share.toFixed(1)}%`} />
            <span className="num-rshare">{l.share < 10 ? l.share.toFixed(1) : Math.round(l.share)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TradeBlock({ flow, t }: { flow: "exports" | "imports"; t: RankedTrade }) {
  const up = flow === "exports";
  return (
    <>
      <RankedList title={`Top ${flow} by product, ${t.year} (${fmt(t.total, "usd")} of goods)`} lines={t.products} flags={false} />
      <RankedList title={`Top ${up ? "destinations" : "origins"}, ${t.year}`} lines={t.partners} flags />
    </>
  );
}

function leaders(a: NumbersActor): string[] {
  const { head_of_state: s, head_of_government: g } = a.leaders;
  if (s && g && s === g) return [`${s} (head of state and government)`];
  return [s ? `${s} (head of state)` : "", g ? `${g} (head of government)` : ""].filter((x) => x !== "");
}

export default function ActorDetail({ a, linked, asOfYear }: { a: NumbersActor; linked: boolean; asOfYear: number }) {
  const lead = leaders(a);
  const sources = [...new Set(Object.values(a.metrics).map((m) => m.source))].filter((s) => SOURCE[s]);
  const trade = a.trade.exports || a.trade.imports;
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">
        <ActorFlag iso2={a.iso2} name={a.name} /> {a.name}
      </p>
      {lead.length > 0 && <p className="geo-pd-meta">{lead.join(" · ")}</p>}
      {GROUPS.map((g) => {
        const rows = g.ids.filter((id) => a.metrics[id]);
        const fuels = g.title === "Energy" && FUELS.some(([, p, c]) => a.metrics[p] || a.metrics[c]);
        if (rows.length === 0 && !fuels) return null;
        return (
          <div key={g.title} className="num-group">
            <p className="geo-micro">{g.title}</p>
            <ul className="num-mrows">
              {rows.map((id) => (
                <Row key={id} id={id} m={a.metrics[id]} asOfYear={asOfYear} />
              ))}
              {fuels && <FuelRows metrics={a.metrics} />}
            </ul>
            {g.title === "Trade" && a.trade.exports && <TradeBlock flow="exports" t={a.trade.exports} />}
            {g.title === "Trade" && a.trade.imports && <TradeBlock flow="imports" t={a.trade.imports} />}
          </div>
        );
      })}
      {!trade && Object.keys(a.metrics).length > 0 && <p className="num-note">No ranked trade on record: this country has not filed merchandise trade with the UN recently.</p>}
      <p className="num-note">
        Annual statistics, each with its own year (not live data); the trend line is the last ten years. Rank is among states.
        {sources.length > 0 && ` Sources: ${sources.map((s) => SOURCE[s]).join("; ")}${trade ? "; WITS / UN Comtrade (trade rankings)" : ""}.`}
      </p>
      {linked && (
        <p className="geo-pd-foot">
          <Link href={`/intel/actors/${a.iso2}`}>Full profile: {a.name} →</Link>
        </p>
      )}
    </div>
  );
}
