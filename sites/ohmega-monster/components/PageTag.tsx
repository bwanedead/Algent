import "./pagetag.css";

// The one page-type marker. Every page wears exactly one, and the six kinds partition the site (docs/architecture/information-architecture.md):
// DAILY (a desk's report for a day), SITUATION (a long-running story's living file), ARTICLE (a deep dive), GLOBE (the HUD),
// DATA (measured layers, no editorial voice) and JUDGMENT (what we think will happen, kept and scored). Sits at the start of the page's kicker line.
export type PageKind = "daily" | "situation" | "article" | "globe" | "data" | "judgment";

const LABEL: Record<PageKind, string> = { daily: "Daily", situation: "Situation", article: "Article", globe: "Globe", data: "Data", judgment: "Judgment" };

export default function PageTag({ kind, detail }: { kind: PageKind; detail?: string }) {
  return (
    <span className={`ptag ptag-${kind}`}>
      <span className="ptag-k">{LABEL[kind]}</span>
      {detail && <span className="ptag-d">{detail}</span>}
    </span>
  );
}
