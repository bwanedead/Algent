import type { EnergyDoc, EnergyTile, SeriesBlock } from "@/lib/live-shared";

import Spark from "./Spark";

// The /live "Energy" section (server component; data is the backend's `live/energy.json`): EU gas storage against the same date
// in earlier years, LNG terminal send-out, and the headline prices as compact tiles. GIE requires a visible source credit on any
// display of AGSI / ALSI data; the credit text and link come with the document and are rendered next to the numbers they cover.

const fmt = (n: number, d = 1) => n.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = (n: number, d = 1) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${fmt(Math.abs(n), d)}`;
const dayLabel = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

function Credit({ c }: { c: { text: string; url: string } }) {
  return (
    <p className="live-credit-line">
      <a className="xt" href={c.url} target="_blank" rel="noopener noreferrer">{c.text}</a>
    </p>
  );
}

function Price({ t }: { t: EnergyTile }) {
  const up = (t.change_pct ?? 0) > 0;
  return (
    <li className="live-etile">
      <p className="live-tile-name">{t.label}</p>
      <p className="live-tile-num">
        <strong>{fmt(t.value, t.value < 10 ? 2 : 1)}</strong> <span className="live-muted">{t.unit}</span>
      </p>
      <p className={`live-tile-note${t.change_pct ? (up ? " is-up" : " is-down") : ""}`}>
        {t.change_pct === null ? "no prior day" : `${sign(t.change_pct, 1)}% on the day`} <span className="live-muted">· {dayLabel(t.as_of_day)}</span>
      </p>
      <Spark values={t.spark} label={`${t.label}, last ${t.spark.length} readings`} width={120} height={28} />
      <p className="live-credit-line">
        <a className="xt" href={t.source_url} target="_blank" rel="noopener noreferrer">{t.source}</a> <span className="live-muted">(delayed)</span>
      </p>
    </li>
  );
}

function Lng({ sendout, full }: { sendout: SeriesBlock | null; full: SeriesBlock | null }) {
  const b = sendout ?? full;
  if (!b) return null;
  const vsAvg = sendout && sendout.avg_30d ? ((sendout.value - sendout.avg_30d) / sendout.avg_30d) * 100 : null;
  return (
    <div className="live-ecard">
      <p className="live-tile-name">EU LNG terminals</p>
      {sendout && (
        <p className="live-tile-num">
          <strong>{fmt(sendout.value, 0)}</strong> <span className="live-muted">GWh/day sent out · {dayLabel(sendout.as_of_day)}</span>
        </p>
      )}
      {vsAvg !== null && <p className="live-tile-note">{sign(vsAvg, 0)}% against the last 30 days&apos; average</p>}
      {sendout && <Spark values={sendout.spark} label="LNG send-out, recent days" />}
      {full && <p className="live-tile-note">Tanks {fmt(full.value, 0)}% full</p>}
    </div>
  );
}

export default function EnergyPanel({ energy }: { energy: EnergyDoc | null }) {
  if (!energy) return <p className="live-empty">Energy numbers appear once the gas and price series have data.</p>;
  const gas = energy.gas;
  return (
    <div className="live-energy">
      {gas && (
        <div className="live-ecard live-ecard-wide">
          <p className="live-tile-name">EU gas storage</p>
          <p className="live-tile-num">
            <strong>{fmt(gas.value)}%</strong> <span className="live-muted">full · {dayLabel(gas.as_of_day)}</span>
            {gas.week_change !== null && <span className="live-muted"> · {sign(gas.week_change)} pts in a week</span>}
          </p>
          <Spark values={gas.spark} band={gas.band} width={260} height={48} label="EU gas storage fill over the last 120 days, with the range of earlier years behind it" />
          {gas.years.length > 0 && (
            <p className="live-tile-note">
              Same date: {gas.years.map((y) => `${y.year} ${fmt(y.value, 0)}%`).join(" · ")}
              <span className="live-muted"> (shaded band: range of those years)</span>
            </p>
          )}
          <Credit c={energy.credits.gas} />
        </div>
      )}
      {energy.lng && (
        <div className="live-ecard">
          <Lng sendout={energy.lng.sendout} full={energy.lng.full} />
          <Credit c={energy.credits.lng} />
        </div>
      )}
      {energy.tiles.length > 0 && <ul className="live-etiles">{energy.tiles.map((t) => <Price key={t.id} t={t} />)}</ul>}
    </div>
  );
}
