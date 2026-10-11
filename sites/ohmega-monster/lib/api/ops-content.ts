import { getAllMeta, getArticle } from "@/lib/articles";

import { apiUrl } from "./ops-desk";
import { abs, arr, badRequest, docObj, enumParam, idParam, isObj, limitParam, lower, notFound, objs, paginate, str, type ApiResult, type Args } from "./util";

// Ops over articles (markdown + the claims twin) and the site-wide text search. Reuses lib/articles.ts and the
// published documents; no new index: search is a bounded in-memory match over titles and headlines.

// ---- articles -------------------------------------------------------------------------------------------

export async function articlesOp(a: Args): Promise<ApiResult> {
  const tag = lower(a.tag);
  const q = lower(a.q);
  const metas = await getAllMeta();
  const rows = metas
    .filter((m) => !tag || m.tags.some((t) => t.toLowerCase() === tag))
    .filter((m) => !q || `${m.title} ${m.dek}`.toLowerCase().includes(q))
    .map((m) => ({
      id: m.slug,
      slug: m.slug,
      title: m.title,
      dek: m.dek,
      published_at: m.published_at || m.date,
      status: m.status,
      tags: m.tags,
      places: m.places,
      cite_as: abs(`/articles/${m.slug}`),
      api_url: apiUrl(`/articles/${m.slug}`),
    }));
  const p = paginate(rows, limitParam(a.limit), a.cursor);
  return {
    data: { articles: p.items, total: p.total },
    as_of: rows[0]?.published_at ?? null,
    cite_as: abs("/"),
    source: "ohmega.article.index",
    next_cursor: p.next_cursor,
    note: "status is the article's own honest label (publishable, needs_hedging, ...). Fetch one article for its claims.",
  };
}

/** Source URLs across a twin's claims: strings or {url} objects. */
function claimSources(claims: unknown): string[] {
  const out = new Set<string>();
  for (const c of objs(claims)) {
    for (const s of arr(c.sources)) {
      const u = isObj(s) ? str(s.url) : str(s);
      if (/^https?:\/\//.test(u)) out.add(u);
    }
  }
  return Array.from(out);
}

export async function articleOp(a: Args): Promise<ApiResult> {
  const slug = idParam("slug", a.slug);
  const art = await getArticle(slug);
  if (!art) throw notFound(`article ${slug}`);
  const twin = await docObj(`data/articles/${slug}.json`);
  const cite = abs(`/articles/${slug}`);
  const claims = twin ? arr(twin.claims) : null;
  return {
    data: {
      id: slug,
      slug,
      title: art.title,
      dek: art.dek,
      published_at: art.published_at || art.date,
      status: art.status,
      tags: art.tags,
      places: art.places,
      quick_take: art.quickTake,
      markdown: art.body,
      receipts_markdown: art.receipts,
      claims,
      sources: claims ? claimSources(claims) : [],
      corrections: twin && arr(twin.corrections).length > 0 ? twin.corrections : art.corrections,
      how_to_cite: twin ? str(twin.how_to_cite) || null : null,
      cite_as: cite,
      api_url: apiUrl(`/articles/${slug}`),
      data_url: twin ? abs(`/data/articles/${slug}.json`) : null,
    },
    as_of: (twin && str(twin.as_of)) || art.published_at || art.date || null,
    cite_as: cite,
    source: twin ? "ohmega.article/1" : "ohmega.article.markdown",
    verification: art.status || undefined,
    note: "claims[] (when present) carry grade: confirmed, likely, contested, unconfirmed/speculative (a lead, not established), opinion (attributed). Grades are our assessment as of as_of.",
  };
}

// ---- search ---------------------------------------------------------------------------------------------

const SEARCH_TYPES = ["article", "theater", "pulse", "brief", "daily", "actor"] as const;
type Hit = { type: (typeof SEARCH_TYPES)[number]; id: string; title: string; text: string; date: string; cite_as: string; api_url: string };

async function corpus(): Promise<Hit[]> {
  const [metas, theaters, pulses, intel, actors] = await Promise.all([
    getAllMeta(),
    docObj("theaters/index.json"),
    docObj("data/pulses.json"),
    docObj("data/intel.json"),
    docObj("data/actors/index.json"),
  ]);
  const hits: Hit[] = [];
  for (const m of metas) {
    hits.push({ type: "article", id: m.slug, title: m.title, text: `${m.dek} ${m.tags.join(" ")}`, date: m.published_at || m.date, cite_as: abs(`/articles/${m.slug}`), api_url: apiUrl(`/articles/${m.slug}`) });
  }
  for (const t of objs(theaters?.theaters)) {
    const id = str(t.theater_id);
    hits.push({ type: "theater", id, title: str(t.name), text: str(t.domain), date: str(t.last_seen), cite_as: abs(`/intel/theaters/${id}`), api_url: apiUrl(`/theaters/${id}`) });
  }
  for (const p of objs(pulses?.pulses)) {
    const id = str(p.id);
    hits.push({ type: "pulse", id, title: str(p.name), text: `${str(p.question)} ${str(p.situation)}`, date: str(p.last_assessed), cite_as: abs("/pulses"), api_url: apiUrl(`/pulses/${id}`) });
  }
  for (const b of objs(intel?.briefs)) {
    const slug = str(b.slug);
    hits.push({ type: "brief", id: slug, title: str(b.title), text: `${str(b.bottom_line)} ${str(b.theater_name)}`, date: str(b.as_of), cite_as: abs(str(b.url) || `/intel/briefs/${slug}`), api_url: apiUrl(`/briefs/${slug}`) });
  }
  for (const d of objs(intel?.daily)) {
    const dom = str(d.domain);
    const date = str(d.date);
    hits.push({ type: "daily", id: `${dom}/${date}`, title: str(d.headline), text: arr(d.theaters).map(str).join(" "), date, cite_as: abs(str(d.url) || `/geopolitics/${date}`), api_url: apiUrl(`/daily/${dom}/${date}`) });
  }
  for (const x of objs(actors?.actors)) {
    const iso = str(x.iso2);
    hits.push({ type: "actor", id: iso, title: str(x.name), text: `${iso} ${str(x.region)}`, date: str(actors?.data_as_of), cite_as: abs(`/intel/actors/${iso}`), api_url: apiUrl(`/actors/${iso}`) });
  }
  return hits.filter((h) => h.title !== "");
}

/** Every query word must appear in title or text; title hits rank first, then newest. */
export async function searchOp(a: Args): Promise<ApiResult> {
  const q = lower(a.q);
  if (q.length < 2) throw badRequest("q must be at least 2 characters");
  if (q.length > 200) throw badRequest("q is too long (200 characters max)");
  const type = enumParam("type", a.type, SEARCH_TYPES);
  const words = q.split(/\s+/).filter(Boolean);
  const scored = (await corpus())
    .filter((h) => !type || h.type === type)
    .map((h) => {
      const title = h.title.toLowerCase();
      const all = `${title} ${h.text.toLowerCase()}`;
      return { h, ok: words.every((w) => all.includes(w)), score: words.filter((w) => title.includes(w)).length };
    })
    .filter((x) => x.ok)
    .sort((x, y) => y.score - x.score || y.h.date.localeCompare(x.h.date));
  const p = paginate(scored.map((x) => ({ type: x.h.type, id: x.h.id, title: x.h.title, date: x.h.date || null, cite_as: x.h.cite_as, api_url: x.h.api_url })), limitParam(a.limit, 20), a.cursor);
  return {
    data: { query: q, results: p.items, total: p.total },
    as_of: null,
    cite_as: abs("/"),
    source: "ohmega.search",
    next_cursor: p.next_cursor,
    note: "Plain text match over titles, headlines and names (not full article text). Fetch a result's api_url for the document.",
  };
}
