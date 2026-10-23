import fs from "node:fs";
import path from "node:path";
import { gunzipSync } from "node:zlib";

import { gate } from "./contract";
import { DATA_BASE } from "./data-base";

// The site's content source (docs/architecture/published-content.md, "storage architecture").
//
//   Published files — every JSON document the site shows is a gzipped object in the public object store (Cloudflare R2) at
//                     `docs/<path>.gz`, written by the worker server (the system of record). The site reads ONLY these files: there is no
//                     database on the read path. NEXT_PUBLIC_DATA_BASE (lib/data-base.ts) is the bucket's public URL.
//   Content files   — TRANSITIONAL fallback (content/ and public/data in the repo), used when the bucket is not configured (local dev) or
//                     does not have a document yet (404). Retire it once `newsroom publish rebuild-all` has filled the bucket.
//
// The two failure rules (read them before changing this file):
//   1. A document the bucket does not have (404) is "not published": null, and the page says nothing is published.
//   2. Any OTHER failure (network error, 5xx, 403, a body that will not parse) THROWS. During ISR regeneration a throwing render keeps the
//      last good page (Next serves the stale page and retries on the next request); returning null would regenerate an EMPTY page and cache
//      it for a whole revalidate window. During `next build` (no last good page exists) a failure degrades to the content files instead of
//      failing the deploy.
//
// Egress: every fetch is cached by Next's data cache per revalidate window, so a document is downloaded at most once per window per region
// however many pages read it. Windows are per product (TTL below), from how often each product really changes, not one global number.

/** Seconds a fetched object is cached, by product. A page's own `export const revalidate` must be a literal, so pages repeat these numbers
 *  (kept equal by the comment on each page). Live layers change every few minutes; a desk's daily twice a day; a corpus rarely. */
export const TTL = {
  live: 120, //        live events / stats / anomalies / maritime live layer: the backend republishes every 3-15 min
  snapshot: 180, //    the live map's first paint (summary, energy, satellite): the stream republishes every 3 min
  maritime: 600, //    the maritime analysis page (30 days of events)
  articles: 900, //    article list and bodies: a handful a day
  fast: 300, //        the views the server refreshes every half hour (home, the globe HUD): they follow the page that mixes them with the live strip
  daily: 1800, //      daily reports, dossiers, actors, feeds, and every other view: published twice a day at most
  tables: 1800, //     sanctions, calendar, geoledger: change a few times a day
  static: 3600, //     basemap, track record, benchmarks, radar editions: slow
} as const;

/** The default window for a plain document read. */
export const REVALIDATE_SECONDS = TTL.daily;

export const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");
const ARTICLES_DIR = path.join(process.cwd(), "content", "articles");
const DATA_DIR = path.join(process.cwd(), "public", "data");
const RADAR_DIR = path.join(process.cwd(), "content", "radar");

export const dataEnabled = (): boolean => DATA_BASE !== "";

/** True while `next build` renders pages: there is no last good page to keep, so a bucket failure must not fail the deploy. */
const building = (): boolean => process.env.NEXT_PHASE === "phase-production-build";

/** The bucket answered with something that is not "this document does not exist". Thrown so the last good page survives. */
export class DataUnavailable extends Error {
  constructor(what: string) {
    super(`published data unavailable: ${what}`);
    this.name = "DataUnavailable";
  }
}

/** Gunzip when the bytes are gzip (the object is stored as application/gzip), parse otherwise (a CDN that already decoded it). */
export function decodeDoc(bytes: Buffer): unknown {
  const raw = bytes.length > 2 && bytes[0] === 0x1f && bytes[1] === 0x8b ? gunzipSync(bytes) : bytes;
  return JSON.parse(raw.toString("utf8"));
}

/** One published document by path ("daily/geopolitics/2026-10-01.json"): the parsed body, null if it is not published (or no bucket is
 *  configured, or its schema major is one this build does not read: lib/contract.ts, which remembers why so a page can say an update is pending), throws DataUnavailable on any other failure (see rule 2 above). */
export async function publishedDoc(rel: string, revalidate: number = TTL.daily): Promise<unknown> {
  if (!dataEnabled()) return null;
  try {
    const res = await fetch(`${DATA_BASE}/docs/${rel}.gz`, { next: { revalidate } });
    if (res.status === 404) return null;
    if (!res.ok) throw new DataUnavailable(`${rel} answered ${res.status}`);
    return gate(rel, decodeDoc(Buffer.from(await res.arrayBuffer())));
  } catch (err) {
    if (building()) return null;
    throw err instanceof DataUnavailable ? err : new DataUnavailable(`${rel}: ${(err as Error).message}`);
  }
}

// ---- documents (daily, theaters, actors, briefs, snapshots, record, radar, agent feeds, and the table-shaped products) -------------
//
// One path model (the document path). The first path segment picks the file fallback:
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

/** One JSON document by its path, e.g. "daily/geopolitics/2026-10-01.json", "radar/2026-09-24-2217.json", "data/intel.json".
 *  The published file wins; a 404 (or no bucket) falls back to the content files. Throws when the bucket is configured but failing. */
export async function intelDoc(rel: string, revalidate: number = TTL.daily): Promise<unknown> {
  const doc = await publishedDoc(rel, revalidate);
  return doc !== null ? doc : readFile(fileRoot(rel));
}

/** A document of a table-shaped product (live events, sanctions, ...): the published file or null. No file fallback exists for these;
 *  the page says nothing is published. */
export async function tableDoc<T>(rel: string, revalidate: number): Promise<T | null> {
  return (await publishedDoc(rel, revalidate)) as T | null;
}

/** File names (not paths) directly inside a document directory, e.g. intelNames("daily/geopolitics"). Read from the small name index the
 *  writer publishes at `docs/_names/<dir>.json.gz` (a bucket cannot be listed from the browser or the site). */
export async function intelNames(dir: string, revalidate: number = TTL.daily): Promise<string[]> {
  const doc = await publishedDoc(`_names/${dir}.json`, revalidate);
  if (Array.isArray(doc) && doc.length > 0) return doc.filter((n): n is string => typeof n === "string" && n !== "" && !n.includes("/"));
  try {
    return fs.readdirSync(fileRoot(dir));
  } catch {
    return [];
  }
}

/** The ".json" names in `dir` without the extension, sorted — the usual "list the slugs" read. */
export async function intelSlugs(dir: string, revalidate: number = TTL.daily): Promise<string[]> {
  return (await intelNames(dir, revalidate)).filter((f) => f.endsWith(".json")).map((f) => f.slice(0, -5)).sort();
}

// ---- articles --------------------------------------------------------------------------------------
// `articles/index.json` carries every article's front matter (no bodies): the list pages fetch one small file, a reader fetches one
// article (`articles/<slug>.json`). The content/articles/*.md files are the fallback.

export type ArticleSource = { slug: string; markdown: string };
export type ArticleFront = { slug: string; data: Record<string, unknown> };

function articleFiles(): string[] {
  return fs.existsSync(ARTICLES_DIR) ? fs.readdirSync(ARTICLES_DIR).filter((f) => f.endsWith(".md")) : [];
}

/** Front matter of every article, newest first as the writer ordered them. `parse` turns a markdown file into its front matter (the
 *  caller owns gray-matter, so this module stays free of it). */
export async function articleFronts(parse: (markdown: string) => Record<string, unknown>): Promise<ArticleFront[]> {
  const doc = (await publishedDoc("articles/index.json", TTL.articles)) as { articles?: { slug?: string; data?: Record<string, unknown> }[] } | null;
  const rows = (doc?.articles ?? []).filter((a): a is ArticleFront => typeof a.slug === "string" && typeof a.data === "object" && a.data !== null);
  if (rows.length > 0) return rows;
  return articleFiles().map((f) => ({ slug: f.replace(/\.md$/, ""), data: parse(fs.readFileSync(path.join(ARTICLES_DIR, f), "utf8")) }));
}

export async function articleSource(slug: string): Promise<ArticleSource | null> {
  if (!/^[\w-]+$/.test(slug)) return null;
  const doc = (await publishedDoc(`articles/${slug}.json`, TTL.articles)) as { markdown?: string } | null;
  if (doc && typeof doc.markdown === "string") return { slug, markdown: doc.markdown };
  const file = path.join(ARTICLES_DIR, `${slug}.md`);
  return fs.existsSync(file) ? { slug, markdown: fs.readFileSync(file, "utf8") } : null;
}
