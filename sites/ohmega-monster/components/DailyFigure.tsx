import { SourceLink } from "@/components/DailyVisuals";
import Popover from "@/components/Popover";
import { assetUrl } from "@/lib/assets";
import type { DailyVisual, VisualKind } from "@/lib/daily";

// An ad-hoc visual the desk drew for a section (backend agents/intel/visuals.py): the picture first, one line
// saying what it shows, the sources, and a tap to enlarge (labels are small on a phone). Drawings that are not
// measurements (schematic, flow) wear a visible tag, in line with the site's AI-images policy.

const KIND: Record<VisualKind, string> = {
  chart: "Chart",
  timeline: "Timeline",
  comparison: "Comparison",
  map: "Map",
  scale: "To scale",
  schematic: "Schematic",
  flow: "Diagram",
  before_after: "Before and after",
};

export default function DailyFigure({ v }: { v: DailyVisual }) {
  const src = assetUrl(v.asset);
  const alt = v.title || v.caption;
  return (
    <figure className={`geo-figure${v.schematic ? " is-schematic" : ""}`}>
      <Popover label={`Enlarge: ${alt}`} triggerClassName="geo-figure-zoom" wide trigger={<img src={src} alt={alt} loading="lazy" />}>
        <div className="geo-pd">
          <p className="geo-pd-title">{v.title}</p>
          <img className="geo-figure-big" src={src} alt={alt} />
          {v.caption && <p className="geo-pd-text">{v.caption}</p>}
        </div>
      </Popover>
      <figcaption>
        <span className="geo-figure-tag">{KIND[v.kind]}</span>
        {v.title && <b className="geo-strong"> {v.title}. </b>}
        <span>{v.caption}</span>
        <span className="geo-figure-src">
          {v.sources.map((s, i) => (s.url ? <SourceLink key={i} url={s.url} label={s.label} /> : <span key={i} className="geo-micro">{s.label}</span>))}
          {v.as_of && <span className="geo-micro">as of {v.as_of}</span>}
          {v.ai_label && <span className="geo-micro">{v.ai_label}</span>}
        </span>
      </figcaption>
    </figure>
  );
}
