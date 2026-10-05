import PulseTile from "@/components/PulseTile";
import type { DossierPulse } from "@/lib/dossier";
import { dayLabel, pulseChange } from "@/lib/dossier-view";
import { BAND_LABEL, findPulse, type Snapshot } from "@/lib/intel";
import { toWallPulse, type WallPulse } from "@/lib/pulse-wall";

import { Overflow } from "./parts";

// The theater's Pulses as small multiples: the shared tile, and under each the same sparkline on the
// SAME 0-100 scale and the SAME time axis, so the eye learns one chart and reads the differences.
// Tiles use the live snapshot reading when the Pulse is there (the same object as on /pulses), else the
// dossier's own copy.

const SHOWN = 6;

type Item = { wall: WallPulse; change: ReturnType<typeof pulseChange> };

function wallFor(snap: Snapshot | null, p: DossierPulse): WallPulse {
  const live = findPulse(snap, p.id, p.name);
  if (live) {
    const sit = snap?.situations.find((s) => s.pulses.includes(live));
    const wall = toWallPulse(live, sit?.title ?? p.situation);
    return p.history.length > wall.history.length ? { ...wall, history: p.history } : wall;
  }
  return {
    id: p.id,
    name: p.name,
    title: p.situation ? `${p.situation} · ${p.name}` : p.name,
    actors_iso2: [],
    situation: p.situation,
    question: "",
    low_end: "",
    high_end: "",
    position: p.position,
    band: p.band,
    confidence: "",
    last_assessed: p.history[p.history.length - 1]?.at ?? "",
    history: p.history,
    rationale: "",
  };
}

const W = 150;
const H = 34;
const PAD = 4;
const yOf = (v: number) => PAD + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - PAD * 2);
const dayOfMs = (t: number) => new Date(t).toISOString().slice(0, 10);

function Spark({ pulse, t0, t1 }: { pulse: WallPulse; t0: number; t1: number }) {
  const pts = pulse.history.slice(-60);
  const times = pts.map((h) => Date.parse(h.at));
  const timed = pts.length > 0 && times.every(Number.isFinite) && t1 > t0;
  const x = (i: number) => PAD + (timed ? (times[i] - t0) / (t1 - t0) : pts.length > 1 ? i / (pts.length - 1) : 1) * (W - PAD * 2);
  const xy = pts.map((h, i) => [x(i), yOf(h.position)] as const);
  const last = xy[xy.length - 1];
  return (
    <svg className={`th-spark intel-band-${pulse.band}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${pulse.title}: ${pts.length} reading${pts.length === 1 ? "" : "s"} on a 0 to 100 scale`}>
      {[25, 50, 75].map((g) => (
        <line key={g} x1={PAD} x2={W - PAD} y1={yOf(g)} y2={yOf(g)} className="th-spark-grid" />
      ))}
      {xy.length > 1 && <path className="th-spark-line" d={xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ")} />}
      {last ? <circle className="th-spark-dot" cx={last[0]} cy={last[1]} r={2.8} /> : <line x1={PAD} x2={W - PAD} y1={H / 2} y2={H / 2} className="th-spark-empty" />}
    </svg>
  );
}

function Cell({ it, t0, t1, anchor }: { it: Item; t0: number; t1: number; anchor: boolean }) {
  return (
    <div className="th-pulse">
      <PulseTile pulse={it.wall} delta={it.change?.delta} period={it.change?.period} size="s" anchor={anchor} />
      <Spark pulse={it.wall} t0={t0} t1={t1} />
    </div>
  );
}

export default function DossierPulses({ pulses, snap }: { pulses: DossierPulse[]; snap: Snapshot | null }) {
  if (pulses.length === 0) return null;
  const items: Item[] = pulses
    .map((p) => wallFor(snap, p))
    .sort((a, b) => (b.position ?? -1) - (a.position ?? -1) || a.name.localeCompare(b.name))
    .map((wall) => ({ wall, change: pulseChange(wall.history, wall.position) }));
  const all = items.flatMap((i) => i.wall.history.map((h) => Date.parse(h.at))).filter(Number.isFinite);
  const t0 = all.length > 0 ? Math.min(...all) : 0;
  const t1 = all.length > 0 ? Math.max(...all) : 0;
  const top = items[0].wall;
  const shown = items.slice(0, SHOWN);
  const rest = items.slice(SHOWN);
  return (
    <section className="th-pulses" aria-labelledby="th-pulses-h">
      <h2 id="th-pulses-h" className="th-h2">
        {top.position !== null
          ? `Hottest Pulse: ${top.title}, ${Math.round(top.position)} of 100 (${BAND_LABEL[top.band].toLowerCase()})`
          : `${items.length} Pulse${items.length === 1 ? "" : "s"}, none assessed yet`}
      </h2>
      <div className="th-pulse-grid">
        {shown.map((it) => (
          <Cell key={it.wall.id} it={it} t0={t0} t1={t1} anchor />
        ))}
      </div>
      {rest.length > 0 && (
        <Overflow label={`All ${items.length} Pulses`} trigger={`${rest.length} more Pulse${rest.length === 1 ? "" : "s"}`} wide>
          <div className="th-pulse-grid">
            {rest.map((it) => (
              <Cell key={it.wall.id} it={it} t0={t0} t1={t1} anchor={false} />
            ))}
          </div>
        </Overflow>
      )}
      {all.length > 1 && t1 > t0 && (
        <p className="th-note">
          Every line: {dayLabel(dayOfMs(t0))} to {dayLabel(dayOfMs(t1))}, on one 0 to 100 scale.
        </p>
      )}
    </section>
  );
}
