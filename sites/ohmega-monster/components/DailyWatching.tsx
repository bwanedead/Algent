import Link from "next/link";

import type { DailyQuiet, DailyWatch } from "@/lib/daily";
import { fmtDay } from "@/lib/daily";
import { dossierPath } from "@/lib/dossier";

// After the theater sections: what the desk is still watching but has nothing new on, and what has gone
// quiet. Compact on purpose: one line each, the dossier one click away.

function Name({ id, name }: { id: string; name: string }) {
  const href = dossierPath(id);
  return href ? <Link href={href}>{name}</Link> : <span>{name}</span>;
}

export default function DailyWatching({ watch, quiet }: { watch: DailyWatch[]; quiet: DailyQuiet[] }) {
  if (watch.length === 0 && quiet.length === 0) return null;
  return (
    <section className="geo-watching" aria-label="Also watching">
      {watch.length > 0 && (
        <>
          <h2 className="geo-h2">Also watching</h2>
          <ul>
            {watch.map((w) => (
              <li key={w.theater_id}>
                <Name id={w.theater_id} name={w.name} /> <span className="geo-micro">{w.note}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {quiet.length > 0 && (
        <>
          <h2 className="geo-h2">Quiet</h2>
          <ul>
            {quiet.map((q) => (
              <li key={q.theater_id}>
                <Name id={q.theater_id} name={q.name} />{" "}
                <span className="geo-micro">
                  {q.countries.length > 0 && `${q.countries.join(", ")} · `}
                  {q.last_novel ? `last change ${fmtDay(q.last_novel)}` : "no recent change"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
