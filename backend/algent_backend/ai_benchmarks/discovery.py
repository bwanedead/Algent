"""
Self-reported discovery — scores that labs post in blogs and model cards days before any leaderboard carries them.

Free first: our own SearXNG finds this week's pages about new models and benchmark results, the pages are fetched and trimmed, and then ONE
low-effort model call extracts (model, org, benchmark, score, date, source url). Everything extracted is stored as ``self_reported`` (the lab's
claim, unverified) and is shown apart from measured scores on the page and in every derived series. Hard limits live in ``flags``: one call a
day, a dollar ceiling a day, a per-call cap enforced by the budget gate, and a switch (``flags.DISCOVERY_ENABLED`` / ``ALGENT_AI_DISCOVERY``).

Nothing is invented by the model: a claim is kept only if its url is one of the pages it was shown and its score is a number it quotes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from . import flags, store
from .contracts import Benchmark, Result, slug
from .labs import lab_of

ROLE = """\
You extract benchmark scores that AI labs CLAIM in their own announcements. You are given the text of a few web pages about newly released AI models.

For each place a page states a score for a named model on a named benchmark, output one claim:
- model: the model name as the page writes it (with the variant if the page says so).
- org: the lab that makes it, if the page says or clearly implies it ("" if not).
- benchmark: the benchmark name as the page writes it (SWE-bench Verified, GPQA Diamond, HLE, ...).
- score: the number exactly as stated (73.4 for "73.4%", 0.734 for 0.734). Never compute, convert or estimate a score.
- unit: "percent" when the page gives a percentage, "fraction" for 0..1, "elo" for Elo ratings, "other" for anything else.
- date: the date of the page's announcement, YYYY-MM-DD, or "" if unknown.
- url: the url of the page the claim comes from, copied from the page header.
- quote: the shortest exact phrase from the page that states the score.

Only the NEW model's own scores. Do not extract scores of competitors that the page lists for comparison, scores of earlier versions, or scores you
remember: only what is written on the pages shown. If a page states no scores, output nothing for it. An empty list is a good answer.
"""


class Claim(BaseModel):
    model: str
    org: str = ""
    benchmark: str
    score: float
    unit: str = "percent"
    date: str = ""
    url: str
    quote: str = ""


class Extraction(BaseModel):
    claims: list[Claim] = Field(default_factory=list)


Search = Callable[[str], list[dict[str, str]]]
FetchPage = Callable[[str], str]
Ask = Callable[[str], tuple[Extraction, float]]


# ── gathering (free) ──────────────────────────────────────────────────────────────────────────────
def default_search(query: str) -> list[dict[str, str]]:
    from algent_backend.agent_system.tools.sourcing.search import searxng

    return searxng.search(query, max_results=flags.DISCOVERY_RESULTS_PER_QUERY, news=True)


def default_fetch_page(url: str) -> str:
    from algent_backend import polite_http
    from algent_backend.library.parse import html_to_text

    return html_to_text(polite_http.get(url))


def seen_urls() -> set[str]:
    out: set[str] = set()
    folder = store.root() / "discovery"
    for p in folder.glob("*.json") if folder.is_dir() else []:
        out |= set(store.load_discovery(p.stem).get("pages", []))
    return out


def gather(search: Search, today: date) -> tuple[list[dict[str, str]], list[str]]:
    """Fresh, unseen result pages across the generic queries (one per host first). Returns (results, errors)."""
    seen, errors, found, hosts = seen_urls(), [], [], set()
    horizon = (today - timedelta(days=flags.DISCOVERY_MAX_AGE_DAYS)).isoformat()
    for q in flags.DISCOVERY_QUERIES:
        try:
            hits = search(q)
        except Exception as exc:  # noqa: BLE001 - SearXNG is localhost-only on the worker; elsewhere it is simply absent
            errors.append(f"{q}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        for h in hits:
            url = h.get("url", "")
            host = url.split("/")[2] if url.count("/") >= 2 else url
            if not url or url in seen or any(f["url"] == url for f in found) or host in hosts:
                continue
            if h.get("published") and h["published"] < horizon:
                continue
            hosts.add(host)
            found.append(h)
    return found, errors


def task_text(pages: list[tuple[dict[str, str], str]], today: date) -> str:
    blocks = [f"=== PAGE url: {h['url']}\ntitle: {h.get('title', '')}\npublished: {h.get('published', 'unknown')}\n{text[:flags.DISCOVERY_PAGE_CHARS]}"
              for h, text in pages]
    return f"TODAY: {today.isoformat()}\n\n" + "\n\n".join(blocks) + "\n\nTASK: extract the lab-claimed benchmark scores stated on these pages."


# ── the one model call ────────────────────────────────────────────────────────────────────────────
def default_ask() -> Ask:
    """task -> (Extraction, usd): the house model at low effort under a per-call cap and the budget gate."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.foundation import cost
    from algent_backend.agent_system.foundation.models import house_spec
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model
    from algent_backend.agent_system.foundation.models.resolver import ModelResolver
    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    spec = house_spec(reasoning_effort="low", temperature=0.0, max_tokens=3072)
    model = gate_chat_model(ModelResolver().resolve(spec).client)
    system = compose_system_prompt(UNIVERSAL_AGENT_BASE, ROLE)

    def ask(task: str) -> tuple[Extraction, float]:
        with cost.scoped(flags.DISCOVERY_CALL_CAP_USD, spec.model):
            out = model.with_structured_output(Extraction).invoke([SystemMessage(content=system), HumanMessage(content=task)])
            led = cost.current_ledger()
            usd = led.spent_usd if led is not None else cost.spent_usd()
        return out, round(float(usd), 6)

    return ask


# ── turning claims into results ───────────────────────────────────────────────────────────────────
def _match(name: str, catalog: dict[str, Benchmark]) -> Benchmark | None:
    """An existing benchmark whose name is the claim's benchmark (compared as slugs; either may carry a suffix: 'Verified', '(agent submissions)')."""
    want = slug(name)
    exact = [b for b in catalog.values() if slug(b.name) == want]
    if exact:
        return exact[0]
    near = [b for b in catalog.values() if b.source != "self_reported" and (slug(b.name).startswith(want + "-") or want.startswith(slug(b.name) + "-"))]
    return min(near, key=lambda b: len(b.name)) if near else None


def to_results(claims: list[Claim], shown: set[str], catalog: dict[str, Benchmark], today: date) -> tuple[list[Benchmark], list[Result]]:
    benches: dict[str, Benchmark] = {}
    results: list[Result] = []
    for c in claims[:flags.DISCOVERY_MAX_CLAIMS]:
        if c.url not in shown or not c.model.strip() or not c.benchmark.strip() or c.score != c.score:
            continue                                            # a url we did not show, or an empty / NaN field, is not a claim
        b = _match(c.benchmark, catalog)
        percent = c.unit == "percent" or (c.unit == "other" and c.score > 1.5 and (b is None or b.unit == "fraction"))
        if b is None:
            bounded = c.unit in ("percent", "fraction")
            b = benches.get(f"claimed-{slug(c.benchmark)}") or Benchmark(
                id=f"claimed-{slug(c.benchmark)}", name=c.benchmark.strip(), source="self_reported", source_url=c.url,
                unit="fraction" if bounded else ("elo" if c.unit == "elo" else "points"), ceiling=1.0 if bounded else None)
            benches[b.id] = b
        score = c.score / 100.0 if (b.unit == "fraction" and (percent or c.score > 1.5)) else c.score
        date_ = c.date if len(c.date) == 10 and c.date[4] == "-" else today.isoformat()
        lab, lab_name = lab_of(c.org)
        results.append(Result(benchmark=b.id, model=c.model.strip(), model_id=c.model.strip(), lab=lab, lab_name=lab_name, score=round(score, 6), date=date_,
                              weights="unknown", verification="self_reported", source="self_reported", url=c.url, observed_on=today.isoformat(),
                              note=" ".join(c.quote.split())[:200]))
    return list(benches.values()), results


# ── the pass ──────────────────────────────────────────────────────────────────────────────────────
def run(*, search: Search | None = None, fetch_page: FetchPage | None = None, ask: Ask | None = None, today: date | None = None,
        dry_run: bool = False) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    day = today.isoformat()
    report: dict[str, Any] = {"day": day, "calls": 0, "usd": 0.0, "claims": 0, "stored": 0, "stopped": ""}
    if not flags.discovery_enabled():
        return {**report, "stopped": "discovery is switched off (ai_benchmarks/flags.DISCOVERY_ENABLED or ALGENT_AI_DISCOVERY=0)"}
    record = store.load_discovery(day)
    if record.get("calls", 0) >= flags.DISCOVERY_MAX_CALLS_PER_DAY or record.get("usd", 0.0) >= flags.DISCOVERY_MAX_USD_PER_DAY:
        return {**report, "calls": record.get("calls", 0), "usd": record.get("usd", 0.0), "stopped": "day limit reached"}
    hits, errors = gather(search or default_search, today)
    report["found"], report["errors"] = len(hits), errors
    fetch_page = fetch_page or default_fetch_page
    pages: list[tuple[dict[str, str], str]] = []
    for h in hits:
        if len(pages) >= flags.DISCOVERY_MAX_PAGES:
            break
        try:
            text = fetch_page(h["url"])
        except Exception as exc:  # noqa: BLE001 - a page that will not load is skipped
            errors.append(f"{h['url']}: {type(exc).__name__}")
            continue
        if len(text.split()) >= 80:
            pages.append((h, text))
    report["pages"] = [h["url"] for h, _ in pages]
    if dry_run or not pages:
        return {**report, "stopped": "dry run" if dry_run else "no new pages to read (no model call made)"}
    try:
        out, usd = (ask or default_ask())(task_text(pages, today))
    except Exception as exc:  # noqa: BLE001 - a refused or failed call ends the pass; the free sources are unaffected
        report["stopped"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        store.save_status("self_reported", last_error=report["stopped"], last_error_at=store.now_iso())
        return report
    benches, results = to_results(out.claims, {h["url"] for h, _ in pages}, store.benchmarks(), today)
    store.save_benchmarks(benches)
    added = store.append(results, existing=store.log())
    report.update(calls=1, usd=round(usd, 6), claims=len(out.claims), stored=added.new + added.revised)
    store.save_discovery(day, {"calls": record.get("calls", 0) + 1, "usd": round(record.get("usd", 0.0) + usd, 6),
                               "pages": sorted(set(record.get("pages", [])) | {h["url"] for h, _ in pages}), "queries": list(flags.DISCOVERY_QUERIES),
                               "claims": [c.model_dump() for c in out.claims]})
    store.save_status("self_reported", last_ok=store.now_iso(), last_error="", broken=False, rows=len(results),
                      newest_result=max((r.date for r in results), default=""), last_new=added.new)
    return report
