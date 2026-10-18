"""
The AI desk's sources — lab blogs, AI research and policy shops, and AI trade press, as library sources (crawled by the same timer as the rest).

Every feed here carries ``beat="ai"``. The geopolitics base excludes these sources (``intel/base.library_heads``) and the AI daily's base is made
of exactly these (``intel/base.ai_library_heads``), so one crawl feeds two desks without mixing their coverage shares. Each entry answered with
fresh items on 2026-10-17; feeds that did not (Microsoft AI 410, Meta AI 400, Anthropic no feed, AISI 404, Lawfare 403, CSIS, and two stale
trade feeds) are not listed. ``company`` = a lab or vendor speaking for itself: primary for what it says it did, never for how well it works.
"""

from __future__ import annotations

from .sources import Source, _rss, _s

AI_BEAT = "ai"


def _ai(id: str, name: str, domain: str, kind: str, url: str, note: str) -> Source:
    return _s(id, name, domain, kind, "global", _rss(url, AI_BEAT), note)


AI_SOURCES: tuple[Source, ...] = (
    # -- labs and vendors speaking for themselves ----------------------------------------------------
    _ai("ai_openai", "OpenAI news", "openai.com", "company", "https://openai.com/news/rss.xml", "OpenAI's own announcements: models, products, policy positions"),
    _ai("ai_deepmind", "Google DeepMind blog", "deepmind.google", "company", "https://deepmind.google/blog/rss.xml", "DeepMind's own research and model announcements"),
    _ai("ai_huggingface", "Hugging Face blog", "huggingface.co", "company", "https://huggingface.co/blog/feed.xml", "the open-weights ecosystem: releases, tooling, community posts"),
    _ai("ai_nvidia", "NVIDIA blog", "blogs.nvidia.com", "company", "https://blogs.nvidia.com/feed/", "the dominant AI chip vendor on its own products, customers and supply"),
    # -- research and policy analysis ----------------------------------------------------------------
    _ai("ai_epoch", "Epoch AI", "epoch.ai", "research", "https://epoch.ai/atom.xml", "independent measurement of compute, data and capability trends (also the source of our benchmark hub)"),
    _ai("ai_cset", "CSET Georgetown", "cset.georgetown.edu", "think_tank", "https://cset.georgetown.edu/feed/", "AI and security policy research: chips, export controls, military AI"),
    _ai("ai_importai", "Import AI", "importai.substack.com", "think_tank", "https://importai.substack.com/feed", "a practitioner's weekly read of AI research and policy"),
    _ai("ai_zvi", "Don't Worry About the Vase", "thezvi.substack.com", "think_tank", "https://thezvi.substack.com/feed", "dense weekly synthesis of AI news, releases and safety debate (an opinionated voice)"),
    # -- trade and technology press ------------------------------------------------------------------
    _ai("ai_mittr", "MIT Technology Review: AI", "technologyreview.com", "regional_news", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "reported AI coverage"),
    _ai("ai_verge", "The Verge: AI", "theverge.com", "regional_news", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "consumer and industry AI coverage"),
    _ai("ai_ars", "Ars Technica: AI", "arstechnica.com", "regional_news", "https://arstechnica.com/ai/feed/", "technical AI reporting"),
    _ai("ai_techcrunch", "TechCrunch: AI", "techcrunch.com", "regional_news", "https://techcrunch.com/category/artificial-intelligence/feed/", "AI startups, funding and product launches"),
    _ai("ai_decoder", "The Decoder", "the-decoder.com", "regional_news", "https://the-decoder.com/feed/", "daily AI model and research news"),
    _ai("ai_wired", "WIRED: AI", "wired.com", "regional_news", "https://www.wired.com/feed/tag/ai/latest/rss", "AI policy, business and culture reporting"),
)

AI_SOURCE_IDS = frozenset(s.id for s in AI_SOURCES)
