import fs from "node:fs";
import path from "node:path";
import { gunzipSync } from "node:zlib";

// The site's content source (docs/architecture/published-content.md).
//
//   Supabase REST  — when NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY are set. Publishing is
//                    a database write; pages pick it up within REVALIDATE_SECONDS, no redeploy.
//   Content files  — TRANSITIONAL fallback (the git-driven path under content/ and public/data). Retire it,
//                    with fileRoot/readFile below, one week after the cut-over to SITE_PUBLISH_VIA="db"
//                    (images already come from Storage — see lib/assets.ts).
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
const DATA_DIR = path.join(process.cwd(), "public", "data");
const RADAR_DIR = path.join(process.cwd(), "content", "radar");

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

/** Rows of a public table (RLS-bounded), for pages that read their own tables (the /live page). [] without a database. */
export async function dbRows<T>(table: string, query: string): Promise<T[]> {
  return (await rest<T>(table, query)) ?? [];
}

const enc = encodeURIComponent;

// ---- documents (daily, theaters, actors, briefs, snapshots, record, radar, agent feeds) ------------
//
// One path model (published_intel_documents.path). The TABLE is only an index (path, kind, storage_key, size, sha256): the document body
// is a gzipped JSON object in the public Storage bucket at `docs/<path>.gz` (backend publishing/doc_store.py; Storage is outside the
// free plan's 500 MB database quota, docs/architecture/database-budget.md). A legacy row that still holds its body inline is read as-is
// until `newsroom db diet` moves it. The first path segment picks the file fallback:
//   data/<rel>   -> public/data/<rel>      the agent feeds (/data/*, situation feeds, article twins)
//   radar/<rel>  -> content/radar/<rel>    headline-radar editions
//   anything else-> content/intel/<path>   the desk's files

function fileRoot(rel: string): string {
  if (rel.startsWith("data/")) return path.join(DATA_DIR, rel.slice(5));
  if (rel.startsWith("radar/")) return path.join(RADAR_DIR, rel.slice(6));
  return path.join(INTEL_DIR, rel);
}

function readFile(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/** A gzipped document object from the public bucket, parsed; null when it is missing or unreadable. The CDN window is short
 *  (the writer sets max-age=60) and the data cache honours REVALIDATE_SECONDS. */
async function storageDoc(key: string): Promise<unknown> {
  if (!dbEnabled()) return null;
  try {
    const res = await fetch(`${BASE}/storage/v1/object/public/published-assets/${key}`, { next: { revalidate: REVALIDATE_SECONDS } });
    if (!res.ok) return null;
    return JSON.parse(gunzipSync(Buffer.from(await res.arrayBuffer())).toString("utf8"));
  } catch {
    return null;
  }
}

/** One JSON document by its path, e.g. "daily/geopolitics/2026-10-01.json", "radar/2026-09-24-2217.json",
 *  "data/intel.json". The index row says where the body is (Storage key, or inline for a not-yet-moved legacy row);
 *  `visible` is enforced by RLS on the row. Null when neither the database nor the files have it. */
export async function intelDoc(rel: string): Promise<unknown> {
  const rows = await rest<{ body: unknown; storage_key: string | null }>(
    "published_intel_documents",
    `select=body,storage_key&path=eq.${enc(rel)}&limit=1`,
  );
  if (rows && rows.length > 0) {
    const row = rows[0];
    if (row.storage_key) {
      const doc = await storageDoc(row.storage_key);
      if (doc !== null) return doc;
    } else if (row.body !== null && row.body !== undefined) {
      return row.body;
    }
  }
  return readFile(fileRoot(rel));
}

/** File names (not paths) directly inside a document directory, e.g. intelNames("daily/geopolitics"). */
export async function intelNames(dir: string): Promise<string[]> {
  const rows = await rest<{ path: string }>("published_intel_documents", `select=path&path=like.${enc(dir + "/")}*&order=path.asc`);
  if (rows && rows.length > 0) {
    return rows.map((r) => r.path.slice(dir.length + 1)).filter((n) => n !== "" && !n.includes("/"));
  }
  try {
    return fs.readdirSync(fileRoot(dir));
  } catch {
    return [];
  }
}

/** The ".json" names in `dir` without the extension, sorted — the usual "list the slugs" read. */
export async function intelSlugs(dir: string): Promise<string[]> {
  return (await intelNames(dir)).filter((f) => f.endsWith(".json")).map((f) => f.slice(0, -5)).sort();
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
