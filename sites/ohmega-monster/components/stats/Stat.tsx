import InfoHover from "@/components/stats/InfoHover";
import { Delta } from "@/components/vl/primitives";
import { statView, type StatInput } from "@/lib/stats/render";

import "./stats.css";

// THE way to render a reader-facing number (docs/architecture/information-architecture.md section 4). Give it a registry id and a value;
// it words the number by its basis (a minimum for our own counts, a mark for model readings, "latest N" for a cap), withholds any "vs usual"
// until our own history is long enough (saying "collecting since 11 Oct" instead), and adds the info hover. Layouts that need their own markup
// call `statView` and `ModelMark` / `InfoHover` directly.

export function ModelMark() {
  return (
    <span className="stat-model" title="Model-assessed: a language model's reading, not a measurement">
      model-assessed
    </span>
  );
}

export default function Stat({ hover = true, unit = false, ...input }: StatInput & { hover?: boolean; unit?: boolean }) {
  const v = statView(input);
  return (
    <span className="stat">
      <span className="stat-n">{v.text}</span>
      {unit && <span className="stat-unit"> {v.def.unit}</span>}
      {v.window && <span className="stat-win"> {v.window}</span>}
      {v.model && <ModelMark />}
      {v.comparison && (v.comparison.sign === 0 ? <span className="stat-cmp">{v.comparison.text}</span> : <Delta text={v.comparison.text} sign={v.comparison.sign} />)}
      {v.collecting && <span className="stat-cmp">{v.collecting}</span>}
      {hover && <InfoHover label={v.def.label} lines={v.lines} />}
    </span>
  );
}
