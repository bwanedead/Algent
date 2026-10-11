import type { Metadata } from "next";

import Scene3D from "@/components/Scene3D";

// Hidden test bench for the interactive 3D viewer (components/Scene3D.tsx): hand-authored example scenes under
// /public/examples, so the viewer can be seen working before any daily has produced one. Not linked, not indexed.
export const metadata: Metadata = {
  title: "Scene lab",
  robots: { index: false, follow: false },
};

const EXAMPLES: Record<string, { title: string; note: string; preview?: string }> = {
  hormuz: { title: "Strait of Hormuz", note: "Coastline from Natural Earth, shipping-lane figures from the U.S. EIA; lane positions approximate (schematic).", preview: "/examples/scene-hormuz.png" },
  scale: { title: "Carrier and submarine to one scale", note: "Dimensions from U.S. Navy fact files, typed by hand: check before relying on them.", preview: "/examples/scene-scale.png" },
  "timeline-demo": { title: "Time scrubber demo", note: "Made-up positions that only exercise the date slider. Not real data." },
};

export default function SceneLab({ searchParams }: { searchParams: { s?: string } }) {
  const key = searchParams.s && searchParams.s in EXAMPLES ? searchParams.s : "hormuz";
  const ex = EXAMPLES[key];
  return (
    <div className="intel-page" style={{ maxWidth: 900, margin: "0 auto", padding: "16px" }}>
      <h1 style={{ fontSize: 20 }}>Scene lab: {ex.title}</h1>
      <p style={{ fontSize: 13 }}>
        {Object.entries(EXAMPLES).map(([k, e]) => (
          <a key={k} href={`/lab/scene?s=${k}`} style={{ marginRight: 12, fontWeight: k === key ? 700 : 400 }}>
            {e.title}
          </a>
        ))}
      </p>
      <Scene3D key={key} src={`/examples/scene-${key}.json`} preview={ex.preview} title={ex.title} />
      <p style={{ fontSize: 12 }}>{ex.note}</p>
    </div>
  );
}
