"use client";

import { useState } from "react";

import { chipUrl, type SceneMeta } from "@/lib/satellite-shared";

import "./satellite.css";

// One site's before / after pair as a slider: the later picture sits on top and is revealed from the left as the handle moves, so the same
// ground can be compared pixel against pixel. The two chips cover the same bbox at the same size. Keyboard: the range input is the control.

export default function BeforeAfter({ name, before, after }: { name: string; before: SceneMeta; after: SceneMeta }) {
  const [at, setAt] = useState(50);
  const b = chipUrl(before.chip);
  const a = chipUrl(after.chip);
  if (!b || !a) return <p className="sat-none">No image storage is configured for this site build.</p>;
  return (
    <figure className="sat-pair">
      <div className="sat-frame">
        {/* plain <img>: the site does not use next/image for bucket assets (docs/architecture/published-content.md) */}
        <img src={b} alt={`${name}, before: Sentinel-2 true colour, ${before.date}`} width={256} height={256} loading="lazy" />
        <img src={a} alt={`${name}, after: Sentinel-2 true colour, ${after.date}`} width={256} height={256} loading="lazy" className="sat-top" style={{ clipPath: `inset(0 ${100 - at}% 0 0)` }} />
        <span className="sat-handle" style={{ left: `${at}%` }} aria-hidden="true" />
        <span className="sat-tag sat-tag-l">{after.date}</span>
        <span className="sat-tag sat-tag-r">{before.date}</span>
      </div>
      <input type="range" min={0} max={100} value={at} onChange={(e) => setAt(Number(e.target.value))} className="sat-range" aria-label={`Slide between the ${after.date} picture (left) and the ${before.date} picture (right)`} />
    </figure>
  );
}
