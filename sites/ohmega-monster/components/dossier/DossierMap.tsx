import { TheaterMapFigure } from "@/components/DailyVisuals";
import type { Dossier } from "@/lib/dossier";

import { VerifyKey } from "./parts";

// The accumulated map: every place the reports have put an event, on one picture. It reuses the daily
// report's map figure (same land, same marks) so the picture is learned once.

export default function DossierMap({ d }: { d: Dossier }) {
  if (!d.map) return null;
  const top = [...d.places].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)).slice(0, 3);
  return (
    <div className="th-map">
      <TheaterMapFigure map={d.map} developments={[]} label={`Map of ${d.map.points.length} place${d.map.points.length === 1 ? "" : "s"} where ${d.name} events were reported.`} />
      <p className="th-note">
        <VerifyKey />
        {top.length > 0 && (
          <>
            {" "}
            · Most reported: {top.map((p) => `${p.name}${p.count > 1 ? ` ×${p.count}` : ""}`).join(", ")}
          </>
        )}
      </p>
    </div>
  );
}
