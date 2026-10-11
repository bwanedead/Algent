import type { ReactNode } from "react";

// THE disclosure pattern of the daily: a native <details> (no JS, keyboard and screen-reader native) whose
// summary wears the blue `.xt` accent. Everything a skimmer can skip sits behind one of these, labelled with
// what is inside it (and how much). Styles: app/geopolitics/geopolitics.css (geo-exp).

export default function Expander({ label, count, hint, children }: { label: string; count?: number; hint?: string; children: ReactNode }) {
  return (
    <details className="geo-exp">
      <summary>
        <span className="xt">{label}</span>
        {count !== undefined && count > 0 && <span className="geo-exp-n"> ({count})</span>}
        {hint && <span className="geo-exp-hint"> · {hint}</span>}
      </summary>
      <div className="geo-exp-body">{children}</div>
    </details>
  );
}
