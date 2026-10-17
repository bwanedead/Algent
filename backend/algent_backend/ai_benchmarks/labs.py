"""
Lab identity — one canonical id and name per organisation, so every chart colours a lab the same way.

Sources spell an organisation many ways ("Google DeepMind", "Google", "Meta AI", "Z.ai (Zhipu AI),Tsinghua University"). The id is the slug of the
FIRST named organisation after the aliases below fold variants together. The alias table only merges spellings; it names no models.
"""

from __future__ import annotations

from .contracts import slug

#: lower-cased spelling -> canonical display name
ALIASES: dict[str, str] = {
    "google deepmind": "Google", "google": "Google", "deepmind": "Google", "google brain": "Google", "google research": "Google",
    "meta ai": "Meta", "meta": "Meta", "facebook": "Meta", "fair": "Meta",
    "z.ai (zhipu ai)": "Z.ai", "zhipu ai": "Z.ai", "z.ai": "Z.ai", "zhipu": "Z.ai",
    "mistral ai": "Mistral", "mistral": "Mistral",
    "microsoft": "Microsoft", "microsoft research": "Microsoft",
    "x.ai": "xAI", "xai": "xAI",
    "alibaba": "Alibaba", "alibaba cloud": "Alibaba", "qwen": "Alibaba",
    "deepseek": "DeepSeek", "deepseek-ai": "DeepSeek",
    "moonshot": "Moonshot", "moonshot ai": "Moonshot",
    "amazon": "Amazon", "amazon web services": "Amazon",
    "openai": "OpenAI", "anthropic": "Anthropic", "nvidia": "NVIDIA",
}


def first_org(org: str) -> str:
    """The first organisation in a source's list. A comma inside parentheses does not split ("Z.ai (Zhipu AI, Tsinghua)")."""
    depth, cur = 0, ""
    for ch in org or "":
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth <= 0:
            break
        cur += ch
    return cur.strip()


def lab_of(org: str) -> tuple[str, str]:
    """(id, display name) for a source's organisation string; ("unknown", "Unknown") when it names none."""
    first = first_org(org)
    if not first:
        return "unknown", "Unknown"
    name = ALIASES.get(first.lower(), first)
    return slug(name), name
