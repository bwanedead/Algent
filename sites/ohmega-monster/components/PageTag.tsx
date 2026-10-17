import "./pagetag.css";

// The one page-type marker. Every page wears exactly one, so a reader always knows which of the three products (or
// which tool) they are in: DAILY (one report a day), THEATER (a living file), ARTICLE (a deep dive), HEADLINES (an
// unverified feed) or TOOL (data and instruments). Sits at the start of the page's kicker line.
export type PageKind = "daily" | "theater" | "article" | "headlines" | "tool";

const LABEL: Record<PageKind, string> = { daily: "Daily", theater: "Theater", article: "Article", headlines: "Headlines", tool: "Tool" };

export default function PageTag({ kind, detail }: { kind: PageKind; detail?: string }) {
  return (
    <span className={`ptag ptag-${kind}`}>
      <span className="ptag-k">{LABEL[kind]}</span>
      {detail && <span className="ptag-d">{detail}</span>}
    </span>
  );
}
