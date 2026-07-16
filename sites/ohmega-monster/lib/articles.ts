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
  date: string;
  status: string; // publishable | needs_hedging | ... (honest, shown to the reader)
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
    .sort((a, b) => (a.date < b.date ? 1 : -1)); // newest first
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
  const receipts = idx >= 0 ? content.slice(idx).trim() : null;
  return { ...toMeta(`${slug}.md`, data), body, receipts };
}

function toMeta(file: string, data: Record<string, unknown>): ArticleMeta {
  return {
    slug: file.replace(/\.md$/, ""),
    title: String(data.title ?? "(untitled)"),
    dek: String(data.dek ?? ""),
    date: String(data.date ?? ""),
    status: String(data.status ?? ""),
  };
}
