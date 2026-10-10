import fs from "node:fs";
import path from "node:path";

// The site's content source (docs/architecture/published-content.md).
//
//   Supabase REST  — when NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY are set. Publishing is
//                    a database write; pages pick it up within REVALIDATE_SECONDS, no redeploy.
//   Content files  — TRANSITIONAL fallback (the git-driven path under content/). Retire it, with
//                    readFile/listFiles below, once the site has run on Supabase in production for a
//                    week and article/analytic assets live in object storage instead of the repo.
//
// Rule: a database answer wins when it has one; an error, or an empty answer (table not yet filled),
// falls back to the files. The anon key is public by design — what it can read is bounded by RLS
// (migration 004): published rows of published_* tables only. No service-role key ever lives here.
// Plain fetch against PostgREST; no client library.

/** 5 minutes: publishes are a handful a day, so staleness of a few minutes is invisible while a page
 *  regenerates at most once per window per instance (cheap on the free tier). */
export const REVALIDATE_SECONDS = 300;

export const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");
const ARTICLES_DIR = path.join(process.cwd(), "content", "articles");

const BASE = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "");
const KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

export const dbEnabled = (): boolean => BASE !== "" && KEY !== "";

/** GET a PostgREST query; null on any failure (the caller falls back to files). */
async function rest<T>(table: string, query: string): Promise<T[] | null> {
  if (!dbEnabled()) return null;
  try {
    const res = await fetch(`${BASE}/rest/v1/${table}?${query}`, {
      headers: { apikey: KEY, Authorization: `Bearer ${KEY}` },
      next: { revalidate: REVALIDATE_SECONDS },
    });
    return res.ok ? ((await res.json()) as T[]) : null;
  } catch {
    return null;
  }
}

const enc = encodeURIComponent;

// ---- intel documents (daily, theaters, actors, briefs, snapshots, record) -------------------------

function readFile(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/** One desk JSON document by its path under the intel directory, e.g. "daily/geopolitics/2026-10-01.json". */
export async function intelDoc(rel: string): Promise<unknown> {
  const rows = await rest<{ body: unknown }>("published_intel_documents", `select=body&path=eq.${enc(rel)}&limit=1`);
  return rows && rows.length > 0 ? rows[0].body : readFile(path.join(INTEL_DIR, rel));
}

/** File names (not paths) directly inside an intel sub-directory, e.g. intelNames("daily/geopolitics"). */
export async function intelNames(dir: string): Promise<string[]> {
  const rows = await rest<{ path: string }>("published_intel_documents", `select=path&path=like.${enc(dir + "/")}*&order=path.asc`);
  if (rows && rows.length > 0) {
    return rows.map((r) => r.path.slice(dir.length + 1)).filter((n) => n !== "" && !n.includes("/"));
  }
  try {
    return fs.readdirSync(path.join(INTEL_DIR, dir));
  } catch {
    return [];
  }
}

// ---- articles --------------------------------------------------------------------------------------

export type ArticleSource = { slug: string; markdown: string };

function articleFiles(): string[] {
  return fs.existsSync(ARTICLES_DIR) ? fs.readdirSync(ARTICLES_DIR).filter((f) => f.endsWith(".md")) : [];
}

export async function articleSources(): Promise<ArticleSource[]> {
  const rows = await rest<ArticleSource>("published_articles", "select=slug,markdown&order=published_at.desc.nullslast");
  if (rows && rows.length > 0) return rows;
  return articleFiles().map((f) => ({ slug: f.replace(/\.md$/, ""), markdown: fs.readFileSync(path.join(ARTICLES_DIR, f), "utf8") }));
}

export async function articleSource(slug: string): Promise<ArticleSource | null> {
  const rows = await rest<ArticleSource>("published_articles", `select=slug,markdown&slug=eq.${enc(slug)}&limit=1`);
  if (rows && rows.length > 0) return rows[0];
  const file = path.join(ARTICLES_DIR, `${slug}.md`);
  return /^[\w-]+$/.test(slug) && fs.existsSync(file) ? { slug, markdown: fs.readFileSync(file, "utf8") } : null;
}
