import { SourceLink } from "@/components/DailyVisuals";
import MapStory from "@/components/MapStory";
import NativeTimeline from "@/components/NativeTimeline";
import Scene3D from "@/components/Scene3D";
import Popover from "@/components/Popover";
import { assetUrl } from "@/lib/assets";
import type { DailyVisual, VisualKind } from "@/lib/daily";

// An ad-hoc visual the desk made for a section (backend agents/intel/visuals.py), routed by kind and shape:
//   - timeline / mapstory with a `spec`: drawn natively and interactively from the data spec (NativeTimeline, MapStory);
//   - scene3d with a `scene`: the 3D viewer (Scene3D);
//   - everything else, including older harness-drawn timelines (no `spec`): the picture first, a tap to enlarge.
// Each has one line saying what it shows and its sources. Drawings that are not measurements (schematic, flow) wear a
// visible tag, in line with the site's AI-images policy.

const KIND: Record<VisualKind, string> = {
  chart: "Chart",
  timeline: "Timeline",
  mapstory: "Map story",
  comparison: "Comparison",
  map: "Map",
  scale: "To scale",
  schematic: "Schematic",
  flow: "Diagram",
  before_after: "Before and after",
  scene3d: "3D scene",
};

export default function DailyFigure({ v }: { v: DailyVisual }) {
  const src = assetUrl(v.asset);
  const alt = v.title || v.caption;
  if (v.kind === "scene3d" && v.scene) {
    return (
      <figure className={`geo-figure${v.schematic ? " is-schematic" : ""}`}>
        <Scene3D src={assetUrl(v.scene)} preview={assetUrl(v.preview)} title={v.title} caption={v.caption} />
        <FigCaption v={v} />
      </figure>
    );
  }
  if (v.kind === "timeline" && v.spec) {
    // Opt-in: a timeline is reference material, not something to scroll past. Collapsed until the reader asks for it.
    return (
      <details className="geo-figure geo-figure-optin">
        <summary className="xt">Timeline: {v.title}</summary>
        <NativeTimeline src={assetUrl(v.spec)} preview={assetUrl(v.preview)} title={v.title} caption={v.caption} />
        <FigCaption v={v} />
      </details>
    );
  }
  if ((v.kind === "timeline" || v.kind === "mapstory") && v.spec) {
    const Native = v.kind === "timeline" ? NativeTimeline : MapStory;
    return (
      <figure className="geo-figure">
        <Native src={assetUrl(v.spec)} preview={assetUrl(v.preview)} title={v.title} caption={v.caption} />
        <FigCaption v={v} />
      </figure>
    );
  }
  return (
    <figure className={`geo-figure${v.schematic ? " is-schematic" : ""}`}>
      <Popover label={`Enlarge: ${alt}`} triggerClassName="geo-figure-zoom" wide trigger={<img src={src} alt={alt} loading="lazy" />}>
        <div className="geo-pd">
          <p className="geo-pd-title">{v.title}</p>
          <img className="geo-figure-big" src={src} alt={alt} />
          {v.caption && <p className="geo-pd-text">{v.caption}</p>}
        </div>
      </Popover>
      <FigCaption v={v} />
    </figure>
  );
}

function FigCaption({ v }: { v: DailyVisual }) {
  return (
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
  );
}
