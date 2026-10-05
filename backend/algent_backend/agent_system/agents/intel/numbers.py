"""
Numbers and power — the structural economics of a theater's actors, and the physical flows around it.

The daily's prose says what happened; this module persists the numbers behind it, deterministically (no model,
no network, stores only), so the page can show WHO the actors are in annual statistics and how those moved over a
decade, not what a market did today:

* ``for_section`` -> a theater's ``numbers`` block: ``actors`` (its principal states: size, energy, trade, public
  finances and balance sheet, military, each with its year, world rank and a ten-year trend, plus the ranked top
  exports/imports by product and by partner) and ``trackers`` (only the dated physical flows and policy rates
  sensing tied to the theater).

What is deliberately NOT here: market prices and exchange rates. A daily price is low information and a stored
price reads as a live quote it is not. A chokepoint's ship count and a central bank's policy rate are different:
physical or structural, slow, dated. ``tracker_ok`` is the one rule.

Nothing here decides what is "unusual": that is ``instruments.moves``. Nothing names a country: actors are the
ones the desk's own records already name (developments' actors, validated places, the brief's relations,
statements' affiliation and counterparts), each passed through ``actors.registry.resolve``, which maps a NAME to a
country and never scans prose. Every function is best-effort: a broken store gives an empty block, never an exception.

BOUNDS (reader budgets or file-size caps, not judgements about the data)
* ``MAX_ACTORS`` = 5: one first-screen group (working memory holds about four to five chunks).
* ``TREND_YEARS`` = 10 annual points per trended metric; ``TOP_RANKED`` = 5 lines per ranked list. A theater's
  block stays near 30 KB with five actors.
* ``SPARK_POINTS`` = 60 for a flow tracker's sparkline (its last year).
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import period_date

MAX_TRACKERS = 8
MAX_ACTORS = 5
TREND_YEARS = 10
TOP_RANKED = 5
SPARK_POINTS = 60
SPARK_DAYS = 365              # the window a sparkline draws: one year, enough to show what "normal" looks like
SPARK_MIN_POINTS = 8          # a series with less than this inside the window (monthly data) draws its last points
SPARK_FALLBACK_POINTS = 24

# What an actor is, in annual statistics, in reading order (ids are the actors catalog's; `energy_production` is the
# profile's derived oil + gas + coal output). Every metric carries its year and world rank; TRENDED ones also their
# last `TREND_YEARS` annual values.
ACTOR_METRICS: tuple[str, ...] = (
    "gdp", "gdp_pc", "population", "gdp_growth",                                            # size and people
    "energy_production", "energy_use", "energy_import_pct",                                 # energy, in total ...
    "oil_prod", "oil_cons", "gas_prod", "gas_cons", "coal_prod", "coal_cons",               # ... and by fuel
    "exports_pct", "imports_pct", "exports_usd", "imports_usd", "fuel_exports_pct",         # trade
    "gov_debt_imf", "fiscal_balance_imf", "current_account_imf", "reserves_usd", "reserves_months",
    "ext_debt_usd", "ext_debt_gni", "policy_rate",                                          # public finances, balance sheet
    "milex", "milex_pct", "armed_forces",                                                   # military
)
TRENDED = frozenset({"gdp", "gdp_pc", "population", "gdp_growth", "energy_use", "exports_pct", "imports_pct",
                     "gov_debt_imf", "fiscal_balance_imf", "current_account_imf", "reserves_usd", "policy_rate",
                     "milex", "milex_pct"})

# Which instrument series may appear as trackers: dated physical flows (chokepoint transits) and central bank
# policy rates. Market prices and exchange rates are not (see the module docstring). ONE rule, one list.
POLICY_RATES = frozenset({"rate_ecb_deposit"})


def tracker_ok(row: dict[str, Any]) -> bool:
    return "chokepoint" in row["tags"] or row["series_id"] in POLICY_RATES


# ── trackers ──────────────────────────────────────────────────────────────────────────────────
def _sig(x: float) -> float:
    return float(f"{x:.6g}")


def spark(series_id: str, day: date) -> list[float]:
    """The series' shape up to ``day``: its last year, evenly downsampled to at most ``SPARK_POINTS`` values
    that always end on the latest reading. A series too sparse for a year (monthly) draws its last points."""
    pts = [(period_date(o.period), o.value) for o in istore.history(series_id) if period_date(o.period) <= day]
    pts.sort()
    if not pts:
        return []
    window = [p for p in pts if (pts[-1][0] - p[0]).days <= SPARK_DAYS]
    if len(window) < SPARK_MIN_POINTS:
        window = pts[-SPARK_FALLBACK_POINTS:]
    vals = [v for _, v in window]
    if len(vals) > SPARK_POINTS:
        step = (len(vals) - 1) / (SPARK_POINTS - 1)
        vals = [vals[round(i * step)] for i in range(SPARK_POINTS)]
    return [_sig(v) for v in vals]


def tracker(row: dict[str, Any], day: date) -> dict[str, Any]:
    """One ``moves_board`` row as a published tracker: latest value, from -> to changes, flags, sparkline.
    An internal-source series (``public_display`` False) is shown with its source named, flagged ``internal``,
    and carries no URL: it is never offered as a citation."""
    changes = {k: {"from": _sig(c["from_value"]), "from_period": c["from_period"],
                   "pct": round(c["pct"], 2) if c["pct"] is not None else None}
               for k, c in row["changes"].items()}
    internal = not row["public_display"]
    return {"id": row["series_id"], "name": row["name"], "unit": row["unit"], "freq": row["frequency"],
            "source": row["source"], "source_url": "" if internal else row["source_url"], "internal": internal,
            "value": _sig(row["latest"]["value"]), "as_of": row["latest"]["period"], "age_days": row["age_days"],
            "changes": changes, "unusual": bool(row["unusual"]), "reasons": list(row["unusual_reasons"]),
            "outside": bool(row["long_run_outside"]), "percentile_1y": row["percentile_1y"],
            "spark": spark(row["series_id"], day)}


def trackers(rows: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """A theater's matched flows and policy rates (``tracker_ok``), unusual ones first then sensing's relevance
    order, at most ``MAX_TRACKERS``."""
    ordered = sorted((r for r in rows if tracker_ok(r)), key=lambda r: not r["unusual"])    # stable inside each half
    return [tracker(r, day) for r in ordered[:MAX_TRACKERS]]


# ── actors ────────────────────────────────────────────────────────────────────────────────────
def _resolve(name: Any) -> str | None:
    """ISO2 for a NAME the desk already chose. A trailing qualifier in brackets ("Iran (Foreign Ministry)")
    is the writer's gloss on the actor, so only the name before it is resolved; the rest is not scanned."""
    from algent_backend.actors import registry

    text = str(name or "").split(" (")[0].strip()
    return registry.resolve(text) if text else None


def actor_codes(section: dict[str, Any], brief: dict | None) -> list[str]:
    """The theater's principal states, most-named first (ties by code): developments' actors (once each),
    validated places' countries, the latest brief's relation endpoints, and the shown statements' speaker
    affiliation and counterparts."""
    hits: Counter[str] = Counter()
    for d in section.get("developments") or []:
        for iso in {i for a in d.get("actors") or [] if (i := _resolve(a))}:
            hits[iso] += 1
        if (iso := _resolve((d.get("place") or {}).get("country"))):
            hits[iso] += 1
    for r in (brief or {}).get("relations") or []:
        for end in ("source", "target"):
            if (iso := _resolve(r.get(end))):
                hits[iso] += 1
    for s in section.get("on_record") or []:
        for iso in {s.get("iso2"), *(s.get("about_iso2") or [])} - {None, ""}:
            hits[str(iso)] += 1
    return [c for c, _ in sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))]


def _ranked(row: Any) -> dict[str, Any]:
    """A stored ranking as {year, total, products[], partners[]}: the top ``TOP_RANKED`` of each, with shares."""
    def top(lines: list[Any], country: bool) -> list[dict[str, Any]]:
        return [{**({"iso2": x.id} if country else {}), "name": x.name, "value": _sig(x.value),
                 "share": round(x.value / row.total * 100, 1)} for x in lines[:TOP_RANKED]]
    return {"year": row.year, "total": _sig(row.total), "products": top(row.products, False),
            "partners": top(row.partners, True)}


def _trends() -> dict[str, dict[str, list[tuple[int, float]]]]:
    """{trended metric: {iso2: [(year, value)...]}} read once per block (derived metrics have no file, no trend)."""
    from algent_backend.actors import store as astore

    out: dict[str, dict[str, list[tuple[int, float]]]] = {}
    for mid in TRENDED:
        by: dict[str, list[tuple[int, float]]] = {}
        for o in astore.history(mid):
            by.setdefault(o.iso2, []).append((o.year, o.value))
        out[mid] = by
    return out


def actor_block(codes: list[str], corpus: Any = None) -> list[dict[str, Any]]:
    """Up to ``MAX_ACTORS`` of ``codes`` that have stored figures, each as ``{iso2, name, leaders, metrics,
    trade}``. ``metrics`` is ``{id: {label, unit, value, year, rank, of, source, trend?}}`` (rank among states;
    ``trend`` = ``[[year, value]...]``, the last ``TREND_YEARS`` years, only for ``TRENDED`` metrics with at least
    three); ``trade`` is ``{exports|imports: {year, total, products[], partners[]}}`` from the WITS ranking."""
    from algent_backend.actors import store as astore
    from algent_backend.actors.profile import load_corpus, profile as actor_profile

    corpus = corpus or load_corpus()
    ranked, trends = astore.latest_trade(), _trends()
    out: list[dict[str, Any]] = []
    for code in codes:
        p = actor_profile(code, corpus)
        if not p:
            continue
        fields = {f["id"]: f for g in p["groups"].values() for f in g}
        metrics: dict[str, Any] = {}
        for mid in ACTOR_METRICS:
            f, rk = fields.get(mid), corpus.rank(mid, p["iso2"])
            if not f:
                continue
            m = {"label": f["label"], "unit": f["unit"], "value": _sig(f["value"]), "year": f["year"],
                 "rank": rk[0] if rk else None, "of": rk[1] if rk else None, "source": f["source"]}
            pts = trends.get(mid, {}).get(p["iso2"], [])[-TREND_YEARS - 1:]
            if len(pts) >= 3:
                m["trend"] = [[y, _sig(v)] for y, v in pts]
            metrics[mid] = m
        lead = p["leadership"]
        leaders = {k: lead[k]["name"] for k in ("head_of_state", "head_of_government") if lead.get(k)}
        trade = {flow: _ranked(ranked[(p["iso2"], flow)]) for flow in ("exports", "imports") if (p["iso2"], flow) in ranked}
        if metrics or leaders:
            out.append({"iso2": p["iso2"], "name": p["name"], "leaders": leaders, "metrics": metrics, "trade": trade})
        if len(out) >= MAX_ACTORS:
            break
    return out


# ── the block ─────────────────────────────────────────────────────────────────────────────────
def for_section(section: dict[str, Any], rows: list[dict[str, Any]], brief: dict | None, *, as_of: str) -> dict[str, Any]:
    """A theater's ``numbers`` block from its finished section, the readings sensing tied to it (``rows`` =
    ``Evidence.instrument_rows``) and its latest brief. Never raises; a part that fails is simply empty."""
    day = date.fromisoformat(as_of)
    out: dict[str, Any] = {"as_of": as_of, "trackers": [], "actors": []}
    try:
        out["trackers"] = trackers(rows, day)
    except Exception as exc:  # noqa: BLE001 - the numbers panel is an aid; it must never cost the report
        out["trackers_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    try:
        out["actors"] = actor_block(actor_codes(section, brief))
    except Exception as exc:  # noqa: BLE001
        out["actors_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out
