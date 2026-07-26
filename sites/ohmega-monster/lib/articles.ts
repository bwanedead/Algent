import fs from "node:fs";
import path from "node:path";

import matter from "gray-matter";

// Articles are plain markdown files with frontmatter, dropped here by the publish pipeline.
// Content-as-files keeps publishing git-driven: approve -> write file -> push -> deploy.
const ARTICLES_DIR = path.join(process.cwd(), "content", "articles");

// The transparency appendix ("the receipts") begins at this heading in the article body. We split
// it out so the page can render it as a collapsible, skippable section.
const RECEIPTS_HEADING = "## How we know this";

export type ArticleMeta = {
  slug: string;
  title: string;
  dek: string;
  date: string; // day-granular, for display
  published_at: string; // full timestamp — what the feed actually sorts on
  status: string; // publishable | needs_hedging | ... (honest, shown to the reader)
  // All derived from the profile by the publish pipeline — never author-written, never generated.
  tags: string[]; // canonical topics first, then the specific entities
  places: string[]; // country display names (aligned with flags when both present)
  flags: string[]; // country flag emoji — rendered as images in the UI (see FlagRow)
  thumbnail: string; // a produced analytic, when the piece has one
  // A generated opening illustration, when the run made one. Decoration, never evidence —
  // which is why the label travels with it and is rendered wherever the image is.
  hero: string;
  heroAlt: string;
  heroHook: string;
  heroLabel: string;
};

export type Article = ArticleMeta & {
  body: string;
  receipts: string | null;
};

function readDir(): string[] {
  if (!fs.existsSync(ARTICLES_DIR)) return [];
  return fs.readdirSync(ARTICLES_DIR).filter((f) => f.endsWith(".md"));
}

export function getAllMeta(): ArticleMeta[] {
  return readDir()
    .map((file) => toMeta(file, matter(fs.readFileSync(path.join(ARTICLES_DIR, file), "utf8")).data))
    // Newest first, on the full publish timestamp — `date` is day-granular, so sorting on it left
    // same-day pieces (routine for a newsroom) in arbitrary order. Falls back to `date` for older
    // articles written before published_at existed.
    .sort((a, b) => (b.published_at || b.date).localeCompare(a.published_at || a.date));
}

export function getSlugs(): string[] {
  return readDir().map((f) => f.replace(/\.md$/, ""));
}

export function getArticle(slug: string): Article | null {
  const file = path.join(ARTICLES_DIR, `${slug}.md`);
  if (!fs.existsSync(file)) return null;
  const { data, content } = matter(fs.readFileSync(file, "utf8"));
  const idx = content.indexOf(RECEIPTS_HEADING);
  const body = (idx >= 0 ? content.slice(0, idx) : content).replace(/^---\s*$/gm, "").trim();
  // The heading is the split marker (a machine contract), not reader copy — the disclosure's own
  // label already says what this is, so drop it from the render rather than say it twice.
  const receipts = idx >= 0 ? content.slice(idx).replace(/^##[^\n]*\n/, "").trim() : null;
  return { ...toMeta(`${slug}.md`, data), body, receipts };
}

function strings(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String).filter(Boolean) : [];
}

function toMeta(file: string, data: Record<string, unknown>): ArticleMeta {
  return {
    slug: file.replace(/\.md$/, ""),
    title: String(data.title ?? "(untitled)"),
    dek: String(data.dek ?? ""),
    date: String(data.date ?? ""),
    published_at: String(data.published_at ?? ""),
    status: String(data.status ?? ""),
    tags: strings(data.tags),
    places: strings(data.places),
    flags: strings(data.flags),
    thumbnail: String(data.thumbnail ?? ""),
    hero: String(data.hero ?? ""),
    heroAlt: String(data.hero_alt ?? ""),
    heroHook: String(data.hero_hook ?? ""),
    heroLabel: String(data.hero_label ?? ""),
  };
}
