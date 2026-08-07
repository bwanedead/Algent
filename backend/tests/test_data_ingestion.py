"""
Offline tests for the data-ingestion pipeline (sources, digest, CLI surface).

No network: parsers run on synthetic batches, lenses/pillars/digest are pure
functions over hand-built records, and the CLI commands run against fake sources.
The live fetch paths (``*_fetch_smoke``) run only when explicitly enabled, so the
default suite stays hermetic.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.data_ingestion.cli import _shared
from algent_backend.data_ingestion.cli import digest as digest_cmd
from algent_backend.data_ingestion.cli import fetch as fetch_cmd
from algent_backend.data_ingestion.cli import insights as insights_cmd
from algent_backend.data_ingestion.cli import sample as sample_cmd
from algent_backend.data_ingestion.cli import sweep as sweep_cmd
from algent_backend.data_ingestion.newsroom.discovery import beats as beats_registry
from algent_backend.data_ingestion.newsroom.discovery import lenses, ranking, sampling
from algent_backend.data_ingestion.newsroom.discovery.candidates import extract_candidates
from algent_backend.data_ingestion.newsroom.discovery.digest import build_digest
from algent_backend.data_ingestion.newsroom.discovery.insights import build_insights
from algent_backend.data_ingestion.newsroom.discovery.memory import (
    RollingMemory,
    load_memory,
    save_memory,
)
from algent_backend.data_ingestion.newsroom.discovery.pillars import pillar_for_theme
from algent_backend.data_ingestion.newsroom.discovery.sweep import run_sweep
from algent_backend.data_ingestion.newsroom.sources import gdelt_doc, gdelt_gkg, gdelt_ngrams
from algent_backend.data_ingestion.newsroom.sources.packet import RawPacket, RawPart
from algent_backend.data_ingestion.newsroom.sources.records import GkgRecord


def _rec(language="eng", themes=(), tone=None, persons=(), organizations=(), url="http://x", **kw) -> GkgRecord:
    return GkgRecord(
        record_id=kw.get("record_id", "r"),
        url=url,
        source_name=kw.get("source_name", "x.com"),
        language=language,
        themes=tuple(themes),
        persons=tuple(persons),
        organizations=tuple(organizations),
        tone=tone,
    )


# -- GKG parsing --------------------------------------------------------------


def _gkg_row(fields: dict[int, str]) -> str:
    row = [""] * 27
    for idx, value in fields.items():
        row[idx] = value
    return "\t".join(row)


def test_parse_row_extracts_fields_and_defaults_language_to_english() -> None:
    row = _gkg_row(
        {
            0: "REC1",
            3: "bbc.com",
            4: "http://bbc.com/a",
            7: "ECON_STOCKMARKET;ENV_CLIMATE;",
            11: "jane doe",
            13: "united nations",
            15: "-3.5,4.0,7.5,11.5",
            25: "",  # empty translation => English source
        }
    )
    [record] = gdelt_gkg.parse_gkg(_zip_bytes(row))
    assert record.record_id == "REC1"
    assert record.url == "http://bbc.com/a"
    assert record.language == "eng"
    assert record.themes == ("ECON_STOCKMARKET", "ENV_CLIMATE")
    assert record.persons == ("jane doe",)
    assert record.organizations == ("united nations",)
    assert record.tone == -3.5


def test_parse_row_reads_source_language_from_translation_info() -> None:
    row = _gkg_row({0: "R", 4: "u", 25: "srclc:fra;eng:Moses;..."})
    [record] = gdelt_gkg.parse_gkg(_zip_bytes(row))
    assert record.language == "fra"


def test_parse_skips_malformed_rows() -> None:
    good = _gkg_row({0: "R", 4: "u"})
    assert len(gdelt_gkg.parse_gkg(_zip_bytes(good + "\n" + "too\tshort"))) == 1


def _zip_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("batch.gkg.csv", text)
    return buf.getvalue()


# -- pillars ------------------------------------------------------------------


def test_pillar_mapping_by_prefix() -> None:
    assert pillar_for_theme("ECON_STOCKMARKET") == "economy"
    assert pillar_for_theme("ENV_CLIMATE") == "environment"
    assert pillar_for_theme("ELECTION_FRAUD") == "politics"
    assert pillar_for_theme("WHATEVER_UNCODED") is None


# -- lenses -------------------------------------------------------------------


def test_volume_lens_ranks_by_frequency() -> None:
    records = [_rec(themes=["A", "B"]), _rec(themes=["A"]), _rec(themes=["A", "C"])]
    assert lenses.volume_lens(records, top=2) == [("A", 3), ("B", 1)] or lenses.volume_lens(
        records, top=2
    ) == [("A", 3), ("C", 1)]


def test_rarity_lens_surfaces_the_long_tail() -> None:
    records = [_rec(themes=["LOUD"]) for _ in range(5)] + [_rec(themes=["NICHE"])]
    rare = lenses.rarity_lens(records, max_count=2)
    assert ("NICHE", 1) in rare
    assert all(theme != "LOUD" for theme, _ in rare)


def test_tone_lens_splits_negative_and_positive_with_support() -> None:
    records = (
        [_rec(themes=["GLOOM"], tone=-8.0) for _ in range(3)]
        + [_rec(themes=["CHEER"], tone=6.0) for _ in range(3)]
        + [_rec(themes=["THIN"], tone=-50.0)]  # below min_support, excluded
    )
    negative, positive = lenses.tone_lens(records, min_support=3)
    assert negative[0][0] == "GLOOM"
    assert positive[0][0] == "CHEER"
    assert all(theme != "THIN" for theme, _, _ in negative + positive)


# -- digest -------------------------------------------------------------------


def test_build_digest_groups_by_language_axis() -> None:
    records = [
        _rec(language="eng", themes=["ECON_STOCKMARKET"], tone=1.0),
        _rec(language="eng", themes=["ECON_STOCKMARKET"], tone=1.0),
        _rec(language="fra", themes=["ENV_CLIMATE"], tone=-2.0),
    ]
    digest = build_digest(records, source="gdelt_gkg", batch_id="20260101000000")

    assert digest.total_records == 3
    assert [lang.language for lang in digest.languages] == ["eng", "fra"]  # largest first
    eng = digest.languages[0]
    assert eng.record_count == 2
    assert eng.pillar_volume == {"economy": 2}
    assert eng.top_themes[0].theme == "ECON_STOCKMARKET"
    assert eng.top_themes[0].pillar == "economy"


# -- NGrams source ------------------------------------------------------------


def test_ngrams_build_packet_counts_records() -> None:
    ndjson = '{"ngram": "a"}\n{"ngram": "b"}\n\n'  # blank line ignored
    gz = gzip.compress(ndjson.encode("utf-8"))
    packet = gdelt_ngrams._build_packet("20260101000100", gz)
    assert packet.source == "gdelt_ngrams"
    assert packet.batch_id == "20260101000100"
    assert len(packet.parts) == 1
    assert packet.parts[0].name == "webngrams.ndjson"
    assert packet.parts[0].record_count == 2


def test_ngrams_latest_packet_url_walks_back_to_first_hit() -> None:
    now = datetime(2026, 1, 1, 0, 10, 0, tzinfo=UTC)
    available = "20260101000700.webngrams.json.gz"  # 3 minutes back

    class _FakeClient:
        def head(self, url):
            return type("R", (), {"status_code": 200 if url.endswith(available) else 404})()

        def close(self):
            pass

    batch_id, url = gdelt_ngrams.latest_packet_url(client=_FakeClient(), now=now)
    assert batch_id == "20260101000700"
    assert url.endswith(available)


# -- CLI ----------------------------------------------------------------------


def test_fetch_cli_lands_raw_parts_and_prints_summary(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    packet = RawPacket(
        source="gdelt_gkg",
        batch_id="20260101000000",
        parts=(
            RawPart(name="english.gkg.csv", text="row1\nrow2\n", record_count=2),
            RawPart(name="translation.gkg.csv", text="row1\n", record_count=1),
        ),
    )
    monkeypatch.setattr(_shared.SOURCES["gdelt_gkg"], "fetch_latest_raw", lambda: packet)

    assert fetch_cmd.run(_ns(source="gdelt_gkg", keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert [p["name"] for p in out["parts"]] == ["english.gkg.csv", "translation.gkg.csv"]
    landed = os.path.join(out["raw_dir"], "english.gkg.csv")
    assert open(landed, encoding="utf-8").read() == "row1\nrow2\n"


def test_digest_cli_writes_digest_and_prints_summary(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    monkeypatch.setitem(
        digest_cmd._FETCHERS,
        "gdelt_gkg",
        lambda: ("20260101000000", [_rec(themes=["ECON_STOCKMARKET"], tone=1.0)]),
    )

    assert digest_cmd.run(_ns(source="gdelt_gkg", keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert out["total_records"] == 1
    assert os.path.exists(out["digest_path"])
    written = json.loads(open(out["digest_path"], encoding="utf-8").read())
    assert written["languages"][0]["language"] == "eng"


# -- retention (one-in-one-out) -----------------------------------------------


def _fake_packet(batch_id: str) -> RawPacket:
    return RawPacket(
        source="gdelt_gkg",
        batch_id=batch_id,
        parts=(RawPart(name="english.gkg.csv", text="row\n", record_count=1),),
    )


def test_fetch_keeps_only_newest_and_reports_purged(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))

    out = {}
    for batch in ("20260101000000", "20260101001500"):
        monkeypatch.setattr(
            _shared.SOURCES["gdelt_gkg"], "fetch_latest_raw", lambda b=batch: _fake_packet(b)
        )
        fetch_cmd.run(_ns(source="gdelt_gkg", keep=1))
        out = json.loads(capsys.readouterr().out)  # drain per fetch; keep the last summary

    remaining = sorted(p.name for p in (tmp_path / "raw" / "gdelt_gkg").iterdir())
    assert remaining == ["20260101001500"]  # only the newest batch survives
    assert out["purged"] == ["20260101000000"]


def test_prune_digest_files_keeps_newest_per_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    d = _shared.digests_dir()
    d.mkdir(parents=True)
    for name in ("gdelt_gkg_20260101000000.json", "gdelt_gkg_20260101001500.json", "other_1.json"):
        (d / name).write_text("{}", encoding="utf-8")

    purged = _shared.prune_digest_files("gdelt_gkg", keep=1)

    assert purged == ["gdelt_gkg_20260101000000.json"]
    survivors = sorted(p.name for p in d.iterdir())
    assert survivors == ["gdelt_gkg_20260101001500.json", "other_1.json"]  # other source untouched


def test_x_grok_scrubs_keys_and_parses_json(monkeypatch) -> None:
    from algent_backend.data_ingestion.newsroom.sources import x_grok_cli

    # Our provider keys must be stripped from the subprocess env.
    monkeypatch.setenv("FIRECRAWL_API_KEY", "secret")
    monkeypatch.setenv("X_BEARER_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    assert "FIRECRAWL_API_KEY" not in x_grok_cli._scrubbed_env()
    assert "X_BEARER_KEY" not in x_grok_cli._scrubbed_env()
    assert "PATH" in x_grok_cli._scrubbed_env()

    def fake_run(cmd, **kw):
        return type("R", (), {"stdout": 'prose…\n[{"topic":"Quake","summary":"big","urls":["http://a"]}]\nmore'})()

    monkeypatch.setattr(x_grok_cli, "run_capturing", fake_run)
    hits = x_grok_cli.fetch_x_grok(limit=5, lanes=("ai",))
    assert hits == [{"topic": "Quake", "summary": "big", "urls": ["http://a"],
                     "lane": "ai", "source": "x_grok"}]


def test_x_grok_fans_out_lanes_and_tags(monkeypatch) -> None:
    from algent_backend.data_ingestion.newsroom.sources import x_grok_cli

    # The lane shows up in the prompt (focus text), so branch the fake on it.
    def fake_run(cmd, **kw):
        prompt = cmd[-1]
        topic = "UFC 320 booked" if "UFC" in prompt else "GPT-6 launch"
        return type("R", (), {"stdout": f'[{{"topic":"{topic}","summary":"s","urls":[]}}]'})()

    monkeypatch.setattr(x_grok_cli, "run_capturing", fake_run)
    hits = x_grok_cli.fetch_x_grok(limit=3, lanes=("ai", "mma"), max_workers=2)
    tagged = {h["topic"]: h["lane"] for h in hits}
    assert tagged == {"GPT-6 launch": "ai", "UFC 320 booked": "mma"}


def test_resolve_lanes_precedence(monkeypatch) -> None:
    from algent_backend.data_ingestion.newsroom.sources import x_grok_cli

    monkeypatch.delenv(x_grok_cli._LANES_ENV, raising=False)
    assert x_grok_cli.resolve_lanes(None) == x_grok_cli._DEFAULT_LANES
    assert x_grok_cli.resolve_lanes(("mma", "bogus")) == ("mma",)  # invalid dropped
    monkeypatch.setenv(x_grok_cli._LANES_ENV, "ai, gaming")
    assert x_grok_cli.resolve_lanes(None) == ("ai", "gaming")
    assert x_grok_cli.resolve_lanes(("nope",)) == x_grok_cli._DEFAULT_LANES  # all-invalid → default


def test_x_native_probe_search_costs_posts(monkeypatch) -> None:
    """When News returns unusable junk, probe falls through to recent search (posts bill)."""
    from algent_backend.data_ingestion.newsroom.sources import x_native

    monkeypatch.setenv("X_BEARER_KEY", "tok")

    class _NewsJunk:
        status_code = 200

        def json(self):
            return {
                "data": [{
                    "id": "junk1",
                    "name": "Celebrity dating drama",
                    "summary": "gossip",
                    "category": "Entertainment",
                    "contexts": {"topics": ["Celebrity"]},
                }],
            }

    class _SearchOk:
        status_code = 200

        def json(self):
            return {
                "data": [{
                    "id": "9", "text": "Breaking: thing happened with officials today about policy",
                    "author_id": "1",
                    "public_metrics": {"like_count": 5, "retweet_count": 1},
                }],
                "includes": {"users": [{"id": "1", "username": "wire"}]},
            }

    class _Client:
        def get(self, url, params=None):
            if "news/search" in url:
                return _NewsJunk()
            return _SearchOk()

        def close(self):
            pass

    out = x_native.fetch_x_native(client=_Client())
    assert out[0]["urls"][0].endswith("/9") and out[0]["likes"] == 5 and out[0]["source"] == "x_api"
    assert x_native.last_cost()["posts_fetched"] == 1
    assert x_native.last_cost()["estimated_usd"] == 0.005


def test_x_api_discovery_uses_news_stories_not_trends(monkeypatch) -> None:
    """General News leg: X News stories (headlines), not WOEID trends."""
    from algent_backend.data_ingestion.newsroom.sources import x_native

    monkeypatch.setenv("X_BEARER_TOKEN", "tok")
    monkeypatch.setenv(x_native._NEWS_SEEDS_ENV, "government")  # one seed for the unit test
    monkeypatch.setenv(x_native._USE_AGGS_ENV, "0")  # isolate News leg
    monkeypatch.setenv(x_native._USE_AI_ENV, "0")
    monkeypatch.setenv(x_native._USE_NOVELTY_ENV, "0")
    monkeypatch.setenv(x_native._USE_SPECTRUM_ENV, "0")
    monkeypatch.setenv(x_native._USE_LISTS_ENV, "0")

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "data": [{
                    "id": "n1",
                    "name": "Something significant happens abroad",
                    "summary": "A concrete development is unfolding with public stakes.",
                    "category": "News",
                    "hook": "What just changed",
                    "keywords": ["diplomacy", "region"],
                    "contexts": {"topics": ["Politics"]},
                }],
            }

    class _Client:
        def get(self, url, params=None):
            assert "news/search" in url
            return _Resp()

        def close(self):
            pass

    hits = x_native.fetch_x_api_discovery(max_stories=10, max_posts=0, client=_Client())
    assert len(hits) == 1
    assert hits[0]["source"] == "x_news"
    assert "significant" in hits[0]["topic"].lower()
    assert hits[0]["lane"].startswith("news:")
    c = x_native.last_cost()
    assert c["posts_fetched"] == 0 and c["trend_requests"] == 0
    assert "news" in c["mode"] and c["news_requests"] >= 1
    assert c["estimated_usd"] == 0.0


def test_x_api_discovery_pulls_general_aggregators(monkeypatch) -> None:
    """Sparse aggregator leg: MarioNawfal-class wires, not a domain roster."""
    from algent_backend.data_ingestion.newsroom.sources import x_native

    monkeypatch.setenv("X_BEARER_TOKEN", "tok")
    monkeypatch.setenv(x_native._USE_NEWS_ENV, "0")
    monkeypatch.setenv(x_native._USE_AI_ENV, "0")
    monkeypatch.setenv(x_native._USE_NOVELTY_ENV, "0")
    monkeypatch.setenv(x_native._USE_SPECTRUM_ENV, "0")
    monkeypatch.setenv(x_native._USE_LISTS_ENV, "0")
    monkeypatch.setenv(x_native._AGGS_ENV, "MarioNawfal")
    monkeypatch.setenv(x_native._AGGS_PER_ENV, "2")

    class _Client:
        def get(self, url, params=None):
            class R:
                def __init__(self, code, body):
                    self.status_code = code
                    self._body = body
                    self.text = str(body)

                def json(self):
                    return self._body

            if "/users/by/username/" in url:
                return R(200, {"data": {"id": "111", "username": "MarioNawfal"}})
            if "/users/111/tweets" in url:
                return R(200, {
                    "data": [
                        {
                            "id": "p1",
                            "text": "BREAKING: officials confirm a major policy shift after overnight talks with allies.",
                            "created_at": "2026-07-22T01:00:00.000Z",
                            "public_metrics": {"like_count": 100, "retweet_count": 20},
                        },
                        {
                            "id": "p2",
                            "text": "Iran strike damage forces Kuwait to urge electricity rationing across the country.",
                            "created_at": "2026-07-22T02:00:00.000Z",
                            "public_metrics": {"like_count": 50, "retweet_count": 10},
                        },
                    ],
                })
            return R(404, {})

        def close(self):
            pass

    hits = x_native.fetch_x_api_discovery(max_stories=10, max_posts=5, client=_Client())
    assert len(hits) == 2
    assert all(h["source"] == "x_aggregator" for h in hits)
    assert hits[0]["author"] == "MarioNawfal"
    assert "MarioNawfal" in hits[0]["lane"]
    c = x_native.last_cost()
    assert c["posts_fetched"] == 2 and c["user_timeline_requests"] == 1
    assert c["estimated_usd"] == 0.01
    assert "aggregators" in c["mode"]


def test_x_api_discovery_ai_pulse_is_dedicated_not_general_only(monkeypatch) -> None:
    """AI pulse is a reserved third leg (labs/people), not a replacement for general News."""
    from algent_backend.data_ingestion.newsroom.sources import x_native

    monkeypatch.setenv("X_BEARER_TOKEN", "tok")
    monkeypatch.setenv(x_native._USE_NEWS_ENV, "0")
    monkeypatch.setenv(x_native._USE_AGGS_ENV, "0")
    monkeypatch.setenv(x_native._USE_NOVELTY_ENV, "0")
    monkeypatch.setenv(x_native._USE_SPECTRUM_ENV, "0")
    monkeypatch.setenv(x_native._USE_LISTS_ENV, "0")
    monkeypatch.setenv(x_native._AI_ACCOUNTS_ENV, "OpenAI,sama")
    monkeypatch.setenv(x_native._AI_NEWS_SEEDS_ENV, "none")
    monkeypatch.setenv(x_native._AI_MAX_POSTS_ENV, "10")

    class _Client:
        def get(self, url, params=None):
            class R:
                def __init__(self, code, body):
                    self.status_code = code
                    self._body = body
                    self.text = str(body)

                def json(self):
                    return self._body

            assert "tweets/search/recent" in url
            q = (params or {}).get("query", "")
            assert "from:OpenAI" in q and "from:sama" in q
            return R(200, {
                "data": [
                    {
                        "id": "a1",
                        "text": "Introducing our new model: stronger reasoning and safer defaults for agents.",
                        "author_id": "1",
                        "public_metrics": {"like_count": 900, "retweet_count": 100},
                    },
                    {
                        "id": "a2",
                        "text": "Excited about the next wave of useful AI tools shipping this quarter.",
                        "author_id": "2",
                        "public_metrics": {"like_count": 50, "retweet_count": 5},
                    },
                ],
                "includes": {"users": [
                    {"id": "1", "username": "OpenAI"},
                    {"id": "2", "username": "sama"},
                ]},
            })

        def close(self):
            pass

    hits = x_native.fetch_x_api_discovery(max_stories=10, max_posts=12, client=_Client())
    assert len(hits) >= 1
    assert all(h["source"] == "x_ai_pulse" for h in hits)
    assert any(h["author"] == "OpenAI" for h in hits)
    assert any(h["lane"].startswith("ai:") for h in hits)
    c = x_native.last_cost()
    assert "ai_pulse" in c["mode"] and c["posts_fetched"] >= 1
    assert c["estimated_usd"] > 0


def test_fetch_polymarket_filters_sports_and_captures_movement() -> None:
    from algent_backend.data_ingestion.newsroom.sources import prediction_markets as pm

    class _Resp:
        status_code = 200

        def json(self):
            return [
                {"question": "Will the Fed cut rates in July?", "outcomes": '["Yes","No"]',
                 "outcomePrices": '["0.6","0.4"]', "volume24hr": 1000, "oneDayPriceChange": 0.05,
                 "lastTradePrice": 0.6, "slug": "fed-cut", "liquidity": 500},
                {"question": "Will Japan win the World Cup?", "outcomes": "[]",
                 "outcomePrices": "[]", "volume24hr": 9999, "slug": "jp"},
                {"question": "Will LeBron James play for the Miami Heat in 2026-27?",
                 "outcomes": "[]", "outcomePrices": "[]", "volume24hr": 5000, "slug": "lbj"},
            ]

    class _Client:
        def get(self, url, params=None):
            return _Resp()

        def close(self):
            pass

    out = pm.fetch_polymarket(client=_Client())
    assert len(out) == 1  # the World Cup market was filtered out
    assert out[0]["question"].startswith("Will the Fed")
    assert out[0]["price_change_1d"] == 0.05 and out[0]["volume_24h"] == 1000.0


def test_build_pool_includes_prediction_markets() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    markets = [{
        "question": "Will X happen by July?", "url": "https://polymarket.com/event/x",
        "last_price": 0.3, "volume_24h": 1000.0, "price_change_1d": 0.1, "source": "polymarket",
    }]
    pool = build_pool(None, None, markets)
    assert pool.by_channel.get("market") == 1
    item = pool.items[0]
    assert item.channel == "market" and item.evidence[0].url.endswith("/x")
    assert item.signals["price_change_1d"] == 0.1


def test_ensure_t0_produces_pool_when_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    from algent_backend.data_ingestion.newsroom.discovery import pipeline

    monkeypatch.setattr(
        pipeline.gdelt_gkg, "fetch_latest",
        lambda: ("20260101000000", [_rec(themes=["ECON_X"], persons=["jane doe"]) for _ in range(5)]),
    )
    msgs: list[str] = []
    pool, path = pipeline.ensure_t0(on_progress=msgs.append)
    assert pool["item_count"] >= 1 and path.endswith(".json")
    assert any("t0 pool ready" in m for m in msgs)


def test_ensure_t0_reuses_a_fresh_pool_without_fetching(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    from algent_backend.data_ingestion.newsroom.discovery import pipeline

    pd = _shared.pool_dir()
    pd.mkdir(parents=True)
    (pd / "pool_20260101.json").write_text('{"item_count": 7, "items": []}', encoding="utf-8")
    fetched: list[int] = []
    monkeypatch.setattr(
        pipeline.gdelt_gkg, "fetch_latest", lambda: fetched.append(1) or ("x", [])
    )
    pool, _ = pipeline.ensure_t0(fresh_minutes=60)
    assert pool["item_count"] == 7 and fetched == []  # reused the fresh pool, no fetch


def test_resolve_channels_precedence(monkeypatch) -> None:
    from algent_backend.data_ingestion.newsroom.discovery import pipeline

    monkeypatch.delenv(pipeline._ENV_CHANNELS, raising=False)
    assert pipeline.resolve_channels(None) == pipeline.DEFAULT_CHANNELS  # default
    assert "x" not in pipeline.DEFAULT_CHANNELS  # X opt-in (sparse yield vs spend)
    assert "x" in pipeline.ALL_CHANNELS  # still available via --channels / env
    # Explicit arg wins, filtered to valid channels.
    assert pipeline.resolve_channels({"gkg", "x", "bogus"}) == frozenset({"gkg", "x"})
    # Env var used when no explicit arg; an all-invalid set falls back to default.
    monkeypatch.setenv(pipeline._ENV_CHANNELS, "gkg, markets")
    assert pipeline.resolve_channels(None) == frozenset({"gkg", "markets"})
    assert pipeline.resolve_channels({"nope"}) == pipeline.DEFAULT_CHANNELS


def test_build_pool_includes_x_news() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    x_hits = [{"topic": "Something significant happens abroad",
               "summary": "A concrete development is unfolding.",
               "urls": [], "source": "x_news", "pre_vetted": False, "lane": "news:World",
               "news_id": "n1", "category": "World"}]
    pool = build_pool(None, None, None, x_hits)
    assert pool.by_channel.get("x") == 1
    item = pool.items[0]
    assert item.channel == "x" and item.kind == "news"
    assert "significant" in item.label.lower()


def test_ensure_t0_x_channel_skips_gkg_and_fetches_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    monkeypatch.setenv("ALGENT_T0_CRYSTALLIZE", "0")  # isolate X path from finisher
    monkeypatch.delenv("ALGENT_X_T0_VIA", raising=False)
    from algent_backend.data_ingestion.newsroom.discovery import pipeline

    gkg_called: list[int] = []
    monkeypatch.setattr(pipeline.gdelt_gkg, "fetch_latest", lambda: gkg_called.append(1) or ("x", []))

    def _fake_api(**_):
        return [{"topic": "Story from X News", "summary": "summary", "urls": [],
                 "source": "x_news", "pre_vetted": False, "lane": "news:World"}]

    monkeypatch.setattr(
        "algent_backend.data_ingestion.newsroom.sources.x_native.fetch_x_api_discovery",
        _fake_api,
    )
    monkeypatch.setattr(
        "algent_backend.data_ingestion.newsroom.sources.x_native.resolve_bearer",
        lambda: "tok",
    )
    monkeypatch.setattr(
        "algent_backend.data_ingestion.newsroom.sources.x_native.last_cost",
        lambda: {"topics": 1, "posts_fetched": 0, "estimated_usd": 0.0,
                 "news_requests": 1, "search_requests": 0, "mode": "news"},
    )
    pool, path = pipeline.ensure_t0(channels={"x"}, on_progress=lambda _m: None)
    assert gkg_called == []  # gkg off → never fetched
    assert pool["by_channel"].get("x") == 1 and path.endswith(".json")


def test_unified_cli_dispatches_ingest_and_runs_categories() -> None:
    from algent_backend.cli.__main__ import _CATEGORIES

    assert {"runs", "ingest"} <= set(_CATEGORIES)   # superset: new categories (e.g. 'site') won't re-break this
    ingest_commands = {m.add_parser.__module__.rsplit(".", 1)[-1] for m in _CATEGORIES["ingest"][1]}
    assert {"fetch", "insights", "sample", "digest", "sources"} <= ingest_commands


# -- candidate extraction -----------------------------------------------------


def test_extract_candidates_covers_themes_and_entities_with_min_count() -> None:
    records = [
        _rec(themes=["ECON_X"], persons=["jane doe"], organizations=["acme"], source_name="a.com"),
        _rec(themes=["ECON_X"], persons=["jane doe"], source_name="b.com"),
        _rec(themes=["ECON_X"], language="spa", source_name="c.com"),
        _rec(themes=["RARE"]),  # below min_count -> dropped
    ]
    stats = {s.full_key: s for s in extract_candidates(records, min_count=2)}

    assert "theme:ECON_X" in stats and "person:jane doe" in stats
    assert "theme:RARE" not in stats
    econ = stats["theme:ECON_X"]
    assert econ.count == 3 and econ.pillar == "economy"
    assert set(econ.languages) == {"eng", "spa"}
    assert econ.source_spread == 3  # three distinct outlets


def test_extract_candidates_captures_example_urls() -> None:
    records = [
        _rec(themes=["ECON_X"], url="http://a"),
        _rec(themes=["ECON_X"], url="http://b"),
        _rec(themes=["ECON_X"], url="http://a"),  # dup url not double-counted
    ]
    [econ] = extract_candidates(records, min_count=2)
    assert econ.examples == ("http://a", "http://b")  # distinct, capped grounding


def test_extract_candidates_drops_boilerplate_themes() -> None:
    records = [_rec(themes=["TAX_FNCACT", "ECON_X", "CRISISLEX_CRISISLEXREC"]) for _ in range(5)]
    keys = {s.full_key for s in extract_candidates(records, min_count=2)}
    assert keys == {"theme:ECON_X"}  # structural GKG tags filtered out


def test_extract_candidates_drops_media_attribution_entities() -> None:
    records = [
        _rec(organizations=["Getty ImagesCredit", "acme corp"], persons=["jane doe"])
        for _ in range(4)
    ]
    keys = {s.full_key for s in extract_candidates(records, min_count=2)}
    assert keys == {"organization:acme corp", "person:jane doe"}  # photo credit dropped


# -- rolling memory + velocity ------------------------------------------------


def test_rolling_memory_baseline_seen_and_window() -> None:
    mem = RollingMemory(source="s")
    assert not mem.has_history and mem.baseline("k") == 0.0

    mem = mem.with_batch("b1", {"k": 10}).with_batch("b2", {"k": 20})
    assert mem.has_history and mem.baseline("k") == 15.0
    assert mem.seen("k") and not mem.seen("other")

    trimmed = mem.with_batch("b3", {"k": 30}, window=2)
    assert [b.batch_id for b in trimmed.batches] == ["b2", "b3"]  # oldest dropped


def test_velocity_is_none_without_history_then_flags_rising() -> None:
    records = [_rec(themes=["ECON_X"]) for _ in range(10)]

    first, counts = build_insights(records, source="s", batch_id="b1", memory=RollingMemory("s"))
    econ_first = next(c for c in first.candidates if c.key == "ECON_X")
    assert first.has_velocity_baseline is False and econ_first.velocity is None

    memory = RollingMemory("s").with_batch("b0", {"theme:ECON_X": 2})  # was small, now 10
    second, _ = build_insights(records, source="s", batch_id="b1", memory=memory)
    econ_second = next(c for c in second.candidates if c.key == "ECON_X")
    assert econ_second.velocity is not None and econ_second.velocity > 0
    assert econ_second.rising and "rising" in econ_second.reasons


# -- ranking protected quota --------------------------------------------------


def test_select_reserves_quota_for_protected_margins() -> None:
    # Loud English themes (count 5), plus one tiny non-English-only outsider (count 3).
    loud = [_rec(themes=[f"LOUD_{i}"], source_name=f"{i}.com") for i in range(20)]
    outsider = [_rec(themes=["OUTSIDER"], language="ukr") for _ in range(3)]
    stats = extract_candidates(loud * 5 + outsider, min_count=3)
    scored = ranking.score_candidates(stats, RollingMemory("s"))

    without_quota = ranking.select(scored, top=5, quota=0)
    with_quota = ranking.select(scored, top=5, quota=2)

    keys_no = {s.candidate.stats.key for s in without_quota}
    keys_yes = {s.candidate.stats.key for s in with_quota}
    assert "OUTSIDER" not in keys_no  # loud incumbents win on raw score
    assert "OUTSIDER" in keys_yes  # quota rescues the non-English margin


def test_curiosity_and_novelty_boost_science_keys() -> None:
    """Science/discovery keys get a curiosity score; novel keys get a large novelty boost."""
    sci = [_rec(themes=["SCIENCE_PHYSICS_BREAKTHROUGH"], source_name=f"s{i}.edu") for i in range(5)]
    bland = [_rec(themes=["LOUD_BLAND"], source_name=f"b{i}.com") for i in range(5)]
    mem = RollingMemory("s").with_batch("b0", {"theme:LOUD_BLAND": 5})  # bland seen; sci novel
    stats = extract_candidates(sci + bland, min_count=3)
    scored = ranking.score_candidates(stats, mem)
    by_key = {c.stats.key: c for c in scored}
    assert by_key["SCIENCE_PHYSICS_BREAKTHROUGH"].curiosity >= 0.75
    assert "curiosity" in by_key["SCIENCE_PHYSICS_BREAKTHROUGH"].reasons
    assert by_key["SCIENCE_PHYSICS_BREAKTHROUGH"].novel is True
    # With novelty+curiosity boosts, the science key should not trail bland volume.
    assert by_key["SCIENCE_PHYSICS_BREAKTHROUGH"].score >= by_key["LOUD_BLAND"].score


def test_broad_themes_demoted_vs_story_candidates() -> None:
    """URL-slug stories outrank standing mega-themes when both are rising."""
    from algent_backend.data_ingestion.newsroom.discovery.stories import (
        extract_story_candidates,
        url_slug_label,
    )

    url = (
        "https://example.com/world/"
        "iran-drones-hit-novospasskoye-refinery-after-talks-collapse.html"
    )
    assert url_slug_label(url) is not None
    stories = [
        _rec(
            themes=["ENV_NATURALGAS"],
            persons=["iran"],
            url=url,
            source_name=f"outlet{i}.com",
        )
        for i in range(4)
    ]
    # Extra pure mega-theme volume without story slugs
    mega = [
        _rec(themes=["ENV_NATURALGAS"], url=f"https://wire.example/a{i}", source_name=f"w{i}.com")
        for i in range(8)
    ]
    mem = RollingMemory("s").with_batch("b0", {"theme:ENV_NATURALGAS": 20})
    stats = extract_candidates(stories + mega, min_count=3) + extract_story_candidates(
        stories + mega, min_count=1
    )
    scored = ranking.score_candidates(stats, mem)
    by_kind = {}
    for c in scored:
        by_kind.setdefault(c.stats.kind, []).append(c)
    assert by_kind.get("story"), "expected at least one story candidate"
    best_story = max(by_kind["story"], key=lambda c: c.score)
    gas = next(c for c in scored if c.stats.key == "ENV_NATURALGAS")
    assert best_story.specificity > gas.specificity
    assert best_story.score > gas.score
    assert "specific" in best_story.reasons


def _pool_of(*items):
    from algent_backend.data_ingestion.newsroom.discovery.report import DiscoveryPool

    return DiscoveryPool(generated_at="t", item_count=len(items), items=list(items))


def _pool_item(pid, label, *, channel="gkg", kind="theme", **signals):
    from algent_backend.data_ingestion.newsroom.discovery.report import PoolItem

    return PoolItem(id=pid, label=label, channel=channel, kind=kind, signals=signals)


class _FakeCrystallizer:
    """Returns a canned decision per id, and records what it was actually asked."""

    last_usd = 0.001

    def __init__(self, decisions):
        self.decisions = decisions
        self.seen = ""

    def complete_json(self, *, system: str, user: str):
        self.seen = user
        return self.decisions


def test_crystallize_repairs_machine_labels_and_drops_non_events() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.crystallize import crystallize_pool

    pool = _pool_of(
        _pool_item("gkg:theme:WB_2811", "collective bargaining", kind="theme", score=2.0),
        _pool_item("gkg:event:fda_approve", "fda :: approve", kind="event", score=3.0),
    )
    fake = _FakeCrystallizer([
        {"id": "gkg:theme:WB_2811", "keep": False, "event": None, "reason": "standing topic"},
        {"id": "gkg:event:fda_approve", "keep": True, "reason": "approval",
         "event": "The FDA approved Merck's oral cholesterol drug enlicitide."},
    ])

    out, result = crystallize_pool(pool, client=fake)

    assert result.mode == "llm" and result.dropped == 1 and result.kept == 1
    repaired = out.items[0]
    assert repaired.label.startswith("The FDA approved")
    assert repaired.signals["raw_label"] == "fda :: approve"   # audit trail kept


def test_crystallize_leaves_published_headlines_alone() -> None:
    """A real headline is not this module's business — no rewrite, no drop, no call."""
    from algent_backend.data_ingestion.newsroom.discovery.crystallize import crystallize_pool

    headline = "Uganda clears final Ebola patient, starting 42-day countdown"
    pool = _pool_of(
        _pool_item("beat:http://a", headline, channel="beat", kind="article"),
        _pool_item("x:x_news:1", "Houthis declare naval blockade", channel="x", kind="news"),
        _pool_item("market:pm:1", "Will the Fed cut in September?", channel="market", kind="market"),
    )
    fake = _FakeCrystallizer([])

    out, result = crystallize_pool(pool, client=fake)

    assert result.mode == "off" and result.kept == 3 and result.dropped == 0
    assert fake.seen == ""                              # the model was never called
    assert [i.label for i in out.items][0] == headline  # headline untouched


def test_crystallize_never_overwrites_a_source_headline_with_generated_text() -> None:
    """Evidence carries the source's own words; model prose must not impersonate them."""
    from algent_backend.data_ingestion.newsroom.discovery.crystallize import crystallize_pool
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatHit

    item = _pool_item("gkg:theme:T", "collective bargaining", kind="theme")
    item.evidence.append(BeatHit(title="Union files for arbitration", url="http://a"))
    fake = _FakeCrystallizer([
        {"id": "gkg:theme:T", "keep": True, "reason": "filing",
         "event": "A rail union filed for federal arbitration over a stalled contract."},
    ])

    out, _ = crystallize_pool(_pool_of(item), client=fake)

    assert out.items[0].label.startswith("A rail union filed")
    assert out.items[0].evidence[0].title == "Union files for arbitration"


def test_sports_text_filtered_from_markets_and_entities() -> None:
    from algent_backend.data_ingestion.newsroom.topic_filters import is_sports_text

    assert is_sports_text("Will LeBron James play for the Miami Heat in 2026-27?")
    assert is_sports_text("Joan Laporta has announced the signing of a Barcelona midfielder")
    assert not is_sports_text("Treasury Secretary Bessent Defends Government Equity Stakes")

    records = [
        _rec(persons=["LeBron James"], organizations=["Miami Heat"], themes=["ECON_X"])
        for _ in range(4)
    ]
    keys = {s.full_key for s in extract_candidates(records, min_count=2)}
    assert "person:LeBron James" not in keys
    assert "organization:Miami Heat" not in keys
    assert "theme:ECON_X" in keys


def test_select_collapses_co_occurring_candidates() -> None:
    # Two entities that always appear together (same 5 records) = one story.
    records = [_rec(persons=["alice"], organizations=["acme corp"]) for _ in range(5)]
    stats = extract_candidates(records, min_count=3)
    selections = ranking.select(ranking.score_candidates(stats, RollingMemory("s")), top=10, quota=0)

    assert len(selections) == 1  # collapsed to a single representative
    rep = selections[0]
    assert rep.related  # the co-occurring entity folded in as related context


# -- sampling -----------------------------------------------------------------


def test_stratified_reservoir_balances_across_languages() -> None:
    import random

    items = [{"lang": "en"} for _ in range(1000)] + [{"lang": "sw"} for _ in range(3)]
    picked = sampling.stratified_reservoir(
        items, size=10, key=lambda r: r["lang"], per_key_cap=5, rng=random.Random(0)
    )
    langs = {r["lang"] for r in picked}
    assert "sw" in langs  # the rare language survives a 1000:3 imbalance


# -- CLI: insights + sample ---------------------------------------------------


def test_insights_cli_writes_report_and_updates_memory(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    records = [_rec(themes=["ECON_X"], persons=["jane doe"]) for _ in range(5)]
    monkeypatch.setitem(insights_cmd._FETCHERS, "gdelt_gkg", lambda: ("20260101000000", records))

    assert insights_cmd.run(_ns(source="gdelt_gkg", keep=1, warmup=0)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert out["has_velocity_baseline"] is False
    assert os.path.exists(out["report_path"])

    # Memory now carries this batch, so a second run has a baseline.
    mem = load_memory("gdelt_gkg", _shared.memory_dir())
    assert mem.has_history and mem.seen("theme:ECON_X")


def test_insights_warmup_backfills_memory_from_preceding_batches(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    latest = [_rec(themes=["ECON_X"]) for _ in range(10)]
    monkeypatch.setitem(insights_cmd._FETCHERS, "gdelt_gkg", lambda: ("20260101010000", latest))
    # Each preceding batch had ECON_X small (count 2) -> latest (10) reads as rising.
    monkeypatch.setitem(
        insights_cmd._BATCH_FETCHERS,
        "gdelt_gkg",
        lambda bid: (bid, [_rec(themes=["ECON_X"]) for _ in range(2)]),
    )

    assert insights_cmd.run(_ns(source="gdelt_gkg", keep=1, warmup=4)) == 0
    report = json.loads(
        open(tmp_path / "insights" / "gdelt_gkg_20260101010000.json", encoding="utf-8").read()
    )
    assert report["has_velocity_baseline"] is True
    econ = next(c for c in report["candidates"] if c["key"] == "ECON_X")
    assert econ["velocity"] is not None and econ["velocity"] > 0 and econ["rising"]


def test_preceding_batch_ids_step_back_15_minutes() -> None:
    ids = insights_cmd._preceding_batch_ids("20260101010000", 3)
    assert ids == ["20260101001500", "20260101003000", "20260101004500"]  # oldest first


def test_sample_cli_writes_stratified_slice(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    stream = (
        {"ngram": f"w{i}", "lang": "en", "pre": "a", "post": "b", "url": "u"} for i in range(50)
    )
    monkeypatch.setitem(sample_cmd._STREAMERS, "gdelt_ngrams", lambda: ("20260101000100", stream))

    assert sample_cmd.run(_ns(source="gdelt_ngrams", size=5, keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["size"] == 5
    written = json.loads(open(out["sample_path"], encoding="utf-8").read())
    assert len(written["records"]) == 5
    assert written["records"][0]["text"]  # snippet assembled from pre/post


# -- beat registry + targeted sweep -------------------------------------------


def test_beat_registry_has_pillars_and_countries() -> None:
    pillars = {b.pillar for b in beats_registry.pillar_beats()}
    assert {"ai", "economics", "finance", "geopolitics", "politics"} <= pillars
    countries = beats_registry.country_beats()
    assert all(b.query.startswith("sourcecountry:") for b in countries)
    assert any(b.country == "China" for b in countries)
    assert beats_registry.all_beats()  # non-empty union


def _beat(bid="pillar:ai", **kw):
    from algent_backend.data_ingestion.newsroom.discovery.beats import Beat

    return Beat(id=bid, label="x", kind="pillar", query="q", **kw)


def test_run_sweep_collects_hits_and_paces_between_beats() -> None:
    slept: list[float] = []
    hit = [{"title": "t", "url": "u", "domain": "d", "country": "United States",
            "language": "English", "seendate": "z"}]
    sheet = run_sweep(
        [_beat("pillar:ai"), _beat("pillar:econ")],
        search=lambda q, **kw: hit,
        sleep=slept.append,
        pace_s=6.0,
    )
    assert sheet.beats_swept == 2 and sheet.beats_failed == 0 and sheet.total_hits == 2
    assert sheet.results[0].hits[0].country == "United States"
    assert slept == [6.0]  # paced once, between the two beats (not before the first)


def test_run_sweep_records_a_throttle_without_retrying_it() -> None:
    """No immediate retry: the retry is the next rotation, when we're out of the penalty box."""
    attempts: list[str] = []

    def always_limited(q, **kw):
        attempts.append(q)
        raise gdelt_doc.RateLimited("slow down")

    sheet = run_sweep([_beat("pillar:ai")], search=always_limited, sleep=lambda _s: None)

    assert attempts == ["q"]  # asked once, not twice
    assert sheet.beats_failed == 1 and sheet.results[0].error == "rate_limited"


def test_run_sweep_resumes_the_gap_the_last_sweep_ended_on() -> None:
    """Starting optimistic every time made the first beats sacrificial — and because a
    throttled beat stays unstamped and so sorts first again, whichever beat led the
    registry burned there forever (pillar:ai never once succeeded)."""
    slept: list[float] = []
    sheet = run_sweep(
        [_beat("pillar:ai"), _beat("pillar:b")], search=lambda q, **kw: [],
        sleep=slept.append, pace_s=10.0, max_gap_s=120.0, start_gap_s=80.0,
        budget_s=10_000.0,
    )
    assert slept == [56.0]           # resumed at 80, decayed on success (80 * 0.7)
    assert sheet.last_gap_s > 10.0   # and the learned pace is carried forward


def test_run_sweep_backs_off_harder_across_beats_while_throttled() -> None:
    """The limiter's state is global, so the gap has to carry across beats, not reset."""
    slept: list[float] = []

    def always_limited(q, **kw):
        raise gdelt_doc.RateLimited("slow down")

    # Raise the consecutive-throttle abort so this test can observe multi-beat backoff.
    run_sweep(
        [_beat(f"pillar:b{i}") for i in range(4)], search=always_limited, sleep=slept.append,
        pace_s=10.0, cooldown_s=20.0, max_gap_s=60.0, budget_s=10_000.0,
        max_consecutive_throttles=10,
    )
    assert slept == [20.0, 40.0, 60.0]  # escalates, then holds at the ceiling


def test_run_sweep_aborts_after_consecutive_throttles() -> None:
    """Once DOC has refused us twice, further asks this cycle only deepen the penalty."""
    attempts: list[str] = []

    def always_limited(q, **kw):
        attempts.append(q)
        raise gdelt_doc.RateLimited("slow down")

    sheet = run_sweep(
        [_beat(f"pillar:b{i}") for i in range(6)],
        search=always_limited,
        sleep=lambda _s: None,
        budget_s=10_000.0,
        max_consecutive_throttles=2,
    )
    assert len(attempts) == 2
    assert sheet.beats_swept == 2
    assert sheet.aborted_for_throttle is True
    assert sheet.last_throttle_at
    assert sheet.beats_failed == 2


def test_run_sweep_relaxes_the_gap_again_after_a_success() -> None:
    calls = [0]

    def limited_then_ok(q, **kw):
        calls[0] += 1
        if calls[0] <= 2:
            raise gdelt_doc.RateLimited("slow down")
        return []

    slept: list[float] = []
    run_sweep(
        [_beat(f"pillar:b{i}") for i in range(5)], search=limited_then_ok, sleep=slept.append,
        pace_s=10.0, cooldown_s=20.0, max_gap_s=60.0, budget_s=10_000.0,
        max_consecutive_throttles=10,
    )
    assert slept[:2] == [20.0, 40.0]
    assert slept[2] == 28.0  # 40 * 0.7 — recovering, not snapping straight back
    assert slept[3] == pytest.approx(19.6)


def test_run_sweep_stops_at_the_wall_clock_budget_leaving_the_rest_unswept() -> None:
    """Unreached beats are omitted, not failed — they were never asked."""
    now = [0.0]

    def clock():
        return now[0]

    def tick(seconds):
        now[0] += seconds

    sheet = run_sweep(
        [_beat(f"pillar:b{i}") for i in range(10)], search=lambda q, **kw: [],
        sleep=tick, clock=clock, pace_s=10.0, budget_s=35.0,
    )
    # 10s per gap against a 35s budget: beats 1-4 fit, the 5th gap would overrun.
    assert sheet.beats_swept == 4 and sheet.beats_failed == 0


def test_sweep_cli_writes_sheet_and_prunes(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    monkeypatch.setattr(
        sweep_cmd, "run_sweep", lambda targets, **kw: _fake_sheet(len(targets))
    )

    code = sweep_cmd.run(_ns(kind="pillar", limit=2, max_records=25, pace=0.0, budget=60.0, keep=1))
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["beats_swept"] == 2
    assert os.path.exists(out["sheet_path"])


def test_sweep_cli_tops_up_the_standing_sheet_instead_of_replacing_it(
    monkeypatch, tmp_path, capsys
) -> None:
    """Sweeping a subset by hand must not discard the beats the rotation gathered."""
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    beats = tmp_path / "beats"
    beats.mkdir()
    real_now = datetime.now(UTC)   # the CLI prunes against the real clock
    (beats / "beats_20260724000000.json").write_text(
        _sheet_with(_stamped("health", 1, _hit("Ebola", "http://e"), base=real_now)
                    ).model_dump_json(),
        encoding="utf-8")
    monkeypatch.setattr(
        sweep_cmd, "run_sweep",
        lambda targets, **kw: _sheet_with(
            _stamped("ai", 0, _hit("Chips", "http://c"), base=real_now)),
    )

    assert sweep_cmd.run(_ns(kind="pillar", limit=1, max_records=25, pace=0.0, budget=60.0, keep=1)) == 0
    out = json.loads(capsys.readouterr().out)

    assert out["beats_swept"] == 1      # this run only asked for one beat
    assert out["sheet_beats"] == 2      # but the sheet still carries the pre-existing one
    merged = json.loads(open(out["sheet_path"], encoding="utf-8").read())
    assert {r["beat_id"] for r in merged["results"]} == {"pillar:ai", "pillar:health"}


def _fake_sheet(n: int):
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatSheet

    return BeatSheet(
        generated_at="2026-01-01T00:00:00+00:00",
        timespan="24h",
        beats_swept=n,
        beats_failed=0,
        total_hits=0,
    )


# -- pool consolidation -------------------------------------------------------


def _insights_with(*candidates):
    from algent_backend.data_ingestion.newsroom.discovery.report import InsightsReport

    return InsightsReport(
        source="gdelt_gkg",
        batch_id="20260101000000",
        generated_at="t",
        total_records=10,
        candidates=list(candidates),
    )


def _candidate(key, kind="theme", pillar=None, **kw):
    from algent_backend.data_ingestion.newsroom.discovery.report import Candidate

    return Candidate(key=key, kind=kind, pillar=pillar, count=kw.get("count", 5), **kw)


def _sheet_with(*results):
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatSheet

    return BeatSheet(
        generated_at="t", timespan="24h", beats_swept=len(results),
        beats_failed=0, total_hits=sum(r.hit_count for r in results), results=list(results),
    )


def _beat_result(pillar, *hits):
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatResult

    return BeatResult(
        beat_id=f"pillar:{pillar}", label=pillar, kind="pillar", pillar=pillar,
        query="q", hit_count=len(hits), hits=list(hits),
    )


def _hit(title, url, country="United States"):
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatHit

    return BeatHit(title=title, url=url, country=country)


def test_build_pool_unifies_channels_aligns_pillars_and_indexes_facets() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    insights = _insights_with(
        _candidate("ECON_X", pillar="economy", rising=True, velocity=2.0),  # aliased -> economics
    )
    sheet = _sheet_with(_beat_result("economics", _hit("Rates rise", "http://a")))

    pool = build_pool(insights, sheet)

    assert pool.by_channel == {"gkg": 1, "beat": 1}
    assert pool.by_pillar["economics"] == 2  # gkg 'economy' aliased to 'economics'
    assert set(pool.facets["economics"]) == {"gkg:theme:ECON_X", "beat:http://a"}
    gkg = next(i for i in pool.items if i.channel == "gkg")
    assert gkg.signals["rising"] is True and gkg.pillars == ["economics"]
    beat = next(i for i in pool.items if i.channel == "beat")
    assert beat.evidence[0].url == "http://a"  # beat item is grounded with the article


def test_build_pool_dedupes_articles_recurring_across_beats() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    same = _hit("Chip deal", "http://x")
    sheet = _sheet_with(_beat_result("ai", same), _beat_result("technology", same))

    pool = build_pool(None, sheet)

    assert pool.item_count == 1  # one article, not two
    assert set(pool.items[0].pillars) == {"ai", "technology"}  # merged tags


def test_build_pool_spends_the_cap_on_unlike_stories_not_on_a_running_one() -> None:
    """The cap buys long tail: near-identical coverage loses slots to anything unlike it."""
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    running = _beat_result(
        "world_events",
        *[_hit(f"Tanker convoy damaged crossing contested strait, day {i}", f"http://w{i}")
          for i in range(10)],
    )
    tail = _beat_result(
        "science",
        _hit("Astronomers report first candidate moon beyond solar system", "http://s1"),
        _hit("Fossil shows juvenile tyrannosaurs hunted alone", "http://s2"),
    )

    pool = build_pool(None, _sheet_with(running, tail), beats_limit=4)
    urls = [i.evidence[0].url for i in pool.items]

    assert "http://s1" in urls and "http://s2" in urls   # the tail survives the cap
    # Ten rewrites of one line are one story. The pool would rather come back short
    # than pad the cap with echoes.
    assert sum(1 for u in urls if u.startswith("http://w")) == 1
    assert len(urls) == 3


def test_truncation_is_source_interleaved_so_list_order_does_not_decide() -> None:
    """When the cap bites, it must not all go to whichever query sorted first.

    Regression: two earlier content-only rules both collapsed here on live data —
    one gave 27 of 28 slots to the first two queries, the other gave 12 to one query
    because non-Latin scripts share no vocabulary and so always looked novel.
    """
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    first = _beat_result(
        "technology",
        *[_hit(f"Chipmaker {n} opens fabrication plant", f"http://t{n}") for n in "abcde"],
    )
    second = _beat_result(
        "health",
        *[_hit(f"Clinic in {n} reports rare parasite cluster", f"http://h{n}") for n in "abcde"],
    )

    urls = [i.evidence[0].url for i in build_pool(None, _sheet_with(first, second),
                                                  beats_limit=4).items]

    assert sum(1 for u in urls if u.startswith("http://t")) > 0
    assert sum(1 for u in urls if u.startswith("http://h")) > 0


def test_a_query_returning_only_echoes_gets_nothing() -> None:
    """No quotas: nothing is owed a slot just for having been asked."""
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    echo = _beat_result(
        "politics",
        *[_hit("Central bank holds rates steady", f"http://e{i}_x") for i in range(3)],
    )
    varied = _beat_result(
        "science",
        _hit("Quantum processor factors record integer", "http://v1"),
        _hit("Archaeologists date Saharan rock art", "http://v2"),
    )
    pool = build_pool(None, _sheet_with(echo, varied), beats_limit=3)
    urls = [i.evidence[0].url for i in pool.items]

    # Three URLs, one headline -> one item, not three.
    assert sum(1 for u in urls if u.startswith("http://e")) == 1
    assert "http://v1" in urls and "http://v2" in urls


def test_build_pool_collapses_the_same_headline_syndicated_to_many_outlets() -> None:
    """A wire story at five URLs is one lead, not five slots in a capped pool."""
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    syndicated = _beat_result(
        "health",
        _hit("U . S . measles cases reach 35 - year high", "http://a"),
        _hit("US measles cases reach 35 year high", "http://b"),   # same headline, other outlet
        _hit("Ebola outbreak tops 1,000 deaths", "http://c"),
    )
    pool = build_pool(None, _sheet_with(syndicated))

    assert pool.item_count == 2
    assert [i.evidence[0].url for i in pool.items] == ["http://a", "http://c"]


def test_build_pool_without_a_beat_cap_keeps_every_hit() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    sheet = _sheet_with(_beat_result("ai", _hit("a", "http://a"), _hit("b", "http://b")))
    assert build_pool(None, sheet).item_count == 2


# -- beat freshness: the rotating refresh -------------------------------------


def _stamped(pillar, hours_ago, *hits, error=None, base=None):
    """A beat result last swept ``hours_ago`` (None = never swept).

    ``base`` defaults to the frozen ``_NOW``; pass the real clock for tests that go
    through code which prunes against ``datetime.now`` (the CLI), so they don't rot.
    """
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatResult

    origin = _NOW if base is None else base
    swept = "" if hours_ago is None else (origin - timedelta(hours=hours_ago)).isoformat()
    return BeatResult(
        beat_id=f"pillar:{pillar}", label=pillar, kind="pillar", pillar=pillar, query="q",
        hit_count=len(hits), hits=list(hits), swept_at=swept, error=error,
    )


_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def test_prune_stale_drops_results_past_their_shelf_life() -> None:
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    sheet = _sheet_with(
        _stamped("science", 2, _hit("fresh", "http://f")),
        _stamped("ai", 700, _hit("month old", "http://o")),   # the dead-sheet case
        _stamped("health", None, _hit("never swept", "http://n")),
    )
    pruned = beat_refresh.prune_stale(sheet, hours=24.0, now=_NOW)

    assert [r.beat_id for r in pruned.results] == ["pillar:science"]
    assert pruned.beats_swept == 1 and pruned.total_hits == 1


def test_prune_stale_returns_none_when_nothing_survives() -> None:
    """A fully stale sheet must contribute nothing — not month-old articles as today's news."""
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    sheet = _sheet_with(_stamped("ai", 700, _hit("old", "http://o")))
    assert beat_refresh.prune_stale(sheet, hours=24.0, now=_NOW) is None
    assert beat_refresh.prune_stale(None) is None


def test_stalest_beats_leads_with_pillars_on_a_cold_start() -> None:
    """Registry order breaks ties, and pillars lead it — so cycle one buys topical breadth."""
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh
    from algent_backend.data_ingestion.newsroom.discovery import beats as registry

    targets = beat_refresh.stalest_beats(None, limit=11, eligible_after=6.0, now=_NOW)

    assert [b.id for b in targets] == [b.id for b in registry.pillar_beats()]


def test_stalest_beats_orders_by_age_and_skips_the_currently_fresh() -> None:
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    fresh = [_beat("pillar:ai"), _beat("pillar:science"), _beat("pillar:health")]
    sheet = _sheet_with(_stamped("ai", 1), _stamped("science", 20), _stamped("health", 8))

    targets = beat_refresh.stalest_beats(
        sheet, limit=5, eligible_after=6.0, registry=fresh, now=_NOW,
    )
    # science (20h) before health (8h); ai (1h) is still current and is not re-swept.
    assert [b.id for b in targets] == ["pillar:science", "pillar:health"]


def test_refresh_sheet_merges_the_slice_and_keeps_untouched_beats() -> None:
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    standing = _sheet_with(
        _stamped("ai", 1, _hit("current ai", "http://ai")),        # fresh — left alone
        _stamped("science", 20, _hit("old science", "http://s0")),  # stale — re-swept
    )
    swept: list[str] = []

    def fake_sweep(targets, **kw):
        swept.extend(b.id for b in targets)
        return _sheet_with(_stamped("science", 0, _hit("new science", "http://s1")))

    merged = beat_refresh.refresh_sheet(
        standing, limit=5, eligible_after=6.0, hours=24.0, now=_NOW, sweep=fake_sweep,
        registry=[_beat("pillar:ai"), _beat("pillar:science")],
    )

    assert swept == ["pillar:science"]  # only the stale one cost a request
    by_id = {r.beat_id: r for r in merged.results}
    assert by_id["pillar:ai"].hits[0].url == "http://ai"     # untouched beat survives
    assert by_id["pillar:science"].hits[0].url == "http://s1"  # stale one replaced


def test_refresh_sheet_keeps_prior_hits_when_a_beat_fails() -> None:
    """A rate-limited beat must not erase its last good coverage — and stays first in line."""
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    standing = _sheet_with(_stamped("science", 20, _hit("last good", "http://s0")))

    def failing_sweep(targets, **kw):
        return _sheet_with(_stamped("science", None, error="rate_limited"))

    merged = beat_refresh.refresh_sheet(
        standing, limit=5, eligible_after=6.0, hours=24.0, now=_NOW, sweep=failing_sweep,
        registry=[_beat("pillar:science")],
    )
    assert merged.results[0].hits[0].url == "http://s0"
    assert merged.results[0].error is None


def test_refresh_sheet_schedules_no_work_when_the_sheet_is_current() -> None:
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh

    standing = _sheet_with(_stamped("science", 1, _hit("fresh", "http://s")))

    def never(targets, **kw):  # pragma: no cover — must not be called
        raise AssertionError("swept a current sheet")

    merged = beat_refresh.refresh_sheet(
        standing, limit=5, eligible_after=6.0, hours=24.0, now=_NOW, sweep=never,
        registry=[_beat("pillar:science")],
    )
    assert merged.results[0].hits[0].url == "http://s"


def test_refresh_sheet_skips_doc_while_cooldown_is_owed() -> None:
    """Do not walk into a DOC limit we already recorded on the standing sheet."""
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatSheet

    standing = BeatSheet(
        generated_at="t",
        timespan="24h",
        beats_swept=1,
        beats_failed=0,
        total_hits=1,
        results=[_stamped("science", 20, _hit("old", "http://s"))],
        last_gap_s=40.0,
        last_throttle_at=_NOW.isoformat(),
    )
    notes: list[str] = []

    def never(targets, **kw):  # pragma: no cover
        raise AssertionError("asked DOC during cooldown")

    merged = beat_refresh.refresh_sheet(
        standing,
        limit=5,
        eligible_after=6.0,
        hours=24.0,
        now=_NOW,
        sweep=never,
        registry=[_beat("pillar:science")],
        on_progress=notes.append,
    )
    assert merged is not None
    assert any("DOC cooldown" in n for n in notes)
    assert merged.results[0].hits[0].url == "http://s"


def test_merge_clears_throttle_stamp_after_a_clean_sweep() -> None:
    from algent_backend.data_ingestion.newsroom.discovery import beat_refresh
    from algent_backend.data_ingestion.newsroom.discovery.report import BeatSheet

    prior = BeatSheet(
        generated_at="t",
        timespan="24h",
        beats_swept=1,
        beats_failed=1,
        total_hits=0,
        results=[_stamped("science", None, error="rate_limited")],
        last_gap_s=40.0,
        last_throttle_at="2026-01-01T00:00:00+00:00",
        aborted_for_throttle=True,
    )
    clean = _sheet_with(_stamped("science", 0, _hit("ok", "http://s")))
    # _sheet_with leaves last_throttle_at empty — merge must adopt that clear.
    merged = beat_refresh.merge(prior, clean)
    assert merged.last_throttle_at == ""
    assert merged.aborted_for_throttle is False
    assert merged.results[0].hits[0].url == "http://s"


def test_run_sweep_stamps_swept_at_on_success_only() -> None:
    ok = run_sweep([_beat("pillar:ai")], search=lambda q, **kw: [], sleep=lambda _s: None)
    assert ok.results[0].swept_at  # stamped -> counts as fresh

    def boom(q, **kw):
        raise RuntimeError("nope")

    failed = run_sweep([_beat("pillar:ai")], search=boom, sleep=lambda _s: None)
    assert failed.results[0].swept_at == ""  # unstamped -> retried next rotation


def test_gkg_theme_labels_humanized_with_code_preserved() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import _humanize_theme, build_pool

    assert _humanize_theme("WB_2811_COLLECTIVE_BARGAINING") == "collective bargaining"
    assert _humanize_theme("TAX_DISEASE_COMA") == "disease coma"
    # An entity (person) keeps its legible key; only theme codes get humanized.
    pool = build_pool(_insights_with(
        _candidate("WB_2811_COLLECTIVE_BARGAINING", kind="theme"),
        _candidate("queen camilla", kind="person"),
    ), None)
    theme = next(i for i in pool.items if i.id.endswith("COLLECTIVE_BARGAINING"))
    assert theme.label == "collective bargaining"
    assert theme.signals["theme_code"] == "WB_2811_COLLECTIVE_BARGAINING"  # raw code kept
    person = next(i for i in pool.items if i.kind == "person")
    assert person.label == "queen camilla"


def test_pool_cli_consolidates_latest_artifacts(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    from algent_backend.data_ingestion.cli import pool as pool_cmd

    insights_dir = tmp_path / "insights"
    insights_dir.mkdir()
    (insights_dir / "gdelt_gkg_20260101000000.json").write_text(
        _insights_with(_candidate("ECON_X", pillar="economy")).model_dump_json(), encoding="utf-8"
    )
    beats_dir = tmp_path / "beats"
    beats_dir.mkdir()
    (beats_dir / "beats_20260101000000.json").write_text(
        _sheet_with(_beat_result("ai", _hit("AI", "http://a"))).model_dump_json(), encoding="utf-8"
    )

    assert pool_cmd.run(_ns(source="gdelt_gkg", keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["item_count"] == 2
    assert os.path.exists(out["pool_path"])


# -- live smokes (opt-in) -----------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ALGENT_LIVE_GKG") != "1",
    reason="live GDELT fetch; set ALGENT_LIVE_GKG=1 to run",
)
def test_gkg_fetch_smoke() -> None:
    batch_id, records = gdelt_gkg.fetch_latest()
    assert len(batch_id) == 14 and batch_id.isdigit()
    assert len(records) > 100


@pytest.mark.skipif(
    os.environ.get("ALGENT_LIVE_NGRAMS") != "1",
    reason="live GDELT fetch; set ALGENT_LIVE_NGRAMS=1 to run",
)
def test_ngrams_fetch_smoke() -> None:
    packet = gdelt_ngrams.fetch_latest_raw()
    assert len(packet.batch_id) == 14 and packet.batch_id.isdigit()
    assert packet.parts[0].record_count > 100


class _ns:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def test_run_sweep_randomises_execution_order_so_no_beat_is_always_first() -> None:
    """Position in a sweep decides who eats the throttle; a fixed order made that a
    permanent sentence (pillar:ai and pillar:science had never once succeeded)."""
    import random as _random

    targets = [_beat(f"pillar:b{i}") for i in range(8)]
    orders = set()
    for seed in range(6):
        seen: list[str] = []

        def _search(q, **kw):
            return []

        sheet = run_sweep(
            targets, search=_search, sleep=lambda _s: None,
            rng=_random.Random(seed), budget_s=10_000.0,
        )
        seen = [r.beat_id for r in sheet.results]
        orders.add(tuple(seen))
        assert sorted(seen) == sorted(b.id for b in targets)  # every beat still swept

    assert len(orders) > 1  # the order actually varies


# -- science feeds: the curiosity channel, off the GDELT chokepoint -------------

_RSS2 = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Orcas filmed smashing giant sunfish</title><link>https://x.org/a</link>
<pubDate>Fri, 25 Jul 2026</pubDate></item>
<item><title>Author Correction: threat coding</title><link>https://x.org/b</link></item>
</channel></rss>"""

_RSS1 = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<item><title>Baby <i>T. rex</i> were killers from birth</title><link>https://nature.com/x</link>
<dc:date>2026-07-25</dc:date></item></rdf:RDF>"""

_ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>How Fast Is the Universe Expanding?</title>
<link href="https://quanta.org/u"/><updated>2026-07-25</updated></entry></feed>"""


def test_science_feed_parses_rss2_rss1_and_atom() -> None:
    """The three shapes these feeds actually ship; Nature is RSS 1.0/RDF."""
    from algent_backend.data_ingestion.newsroom.sources import science_feeds

    rss2 = science_feeds.parse_feed(_RSS2)
    assert rss2[0]["title"] == "Orcas filmed smashing giant sunfish"
    assert rss2[0]["domain"] == "x.org"

    rss1 = science_feeds.parse_feed(_RSS1)
    # Nature italicises species names inline; the markup must not reach the label.
    assert rss1[0]["title"] == "Baby T. rex were killers from birth"

    atom = science_feeds.parse_feed(_ATOM)
    assert atom[0]["url"] == "https://quanta.org/u"   # Atom carries the link as an attr


def test_science_fetch_drops_journal_furniture_and_survives_a_dead_feed() -> None:
    from algent_backend.data_ingestion.newsroom.sources import science_feeds

    class _Resp:
        def __init__(self, code, body=b""):
            self.status_code, self.content = code, body

    class _Client:
        def get(self, url):
            if "dead" in url:
                raise RuntimeError("connection reset")
            return _Resp(200, _RSS2)

    hits = science_feeds.fetch_science(
        feeds=(("dead", "https://dead/", "science"), ("ok", "https://ok/", "science")),
        client=_Client(),
    )
    titles = [h["title"] for h in hits]
    assert titles == ["Orcas filmed smashing giant sunfish"]   # correction dropped
    assert hits[0]["feed"] == "ok" and hits[0]["pillar"] == "science"


def test_build_pool_carries_science_as_its_own_channel() -> None:
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    science = [
        {"title": "Ancient ape fossil in Egypt challenges human origins",
         "url": "https://sd.com/a", "domain": "sd.com", "feed": "science_daily", "pillar": "science"},
        {"title": "Orcas filmed smashing giant sunfish into pieces",
         "url": "https://sd.com/b", "domain": "sd.com", "feed": "science_daily", "pillar": "science"},
    ]
    pool = build_pool(None, None, None, None, science)

    assert pool.by_channel == {"science": 2}
    assert pool.by_pillar["science"] == 2
    item = pool.items[0]
    assert item.channel == "science" and item.kind == "article"
    assert item.signals["found_by"] == "science:science_daily"   # interleave key set


def test_science_channel_screens_the_shared_denylist() -> None:
    """Sports and promo shapes are dropped here as on every other channel."""
    from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool

    science = [
        {"title": "Quantum effect boosts energy transfer", "url": "https://a/1", "feed": "f", "pillar": "science"},
        {"title": "Lakers sign a new center", "url": "https://a/2", "feed": "f", "pillar": "science"},
    ]
    pool = build_pool(None, None, None, None, science)
    assert [i.label for i in pool.items] == ["Quantum effect boosts energy transfer"]
