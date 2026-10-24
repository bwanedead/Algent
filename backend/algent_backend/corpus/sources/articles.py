"""
Published articles (the site's content files): one document each, with its tags as topics and its places as mentions. An article's claims are
the claims of the research profile it was written from, which are already in the index through the profiles source.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.ops.products import locations
from algent_backend.publishing.publish import front_matter

from .. import flags
from ..norm import day, slug
from ..sink import Sink
from .base import Source, Unit, file_digest, mark, rel


def _emit(path, sink: Sink) -> None:                                        # noqa: ANN001 - pathlib.Path
    text = path.read_text(encoding="utf-8")
    fm = front_matter(text)
    end = text.find("\n---", 3) if text.startswith("---") else -1
    body = text[end + 4:] if end > 0 else text
    doc = f"article:{path.stem}"
    when = day(fm.get("published_at")) or day(fm.get("date"))
    sink.document(doc, "article", date=when, title=str(fm.get("title") or path.stem), url=f"/articles/{path.stem}", status=str(fm.get("status") or ""),
                  body=f"{fm.get('dek') or ''}\n{body}")
    for tag in fm.get("tags") or []:
        tid = f"topic:{slug(tag)}"
        sink.declare(tid, "topic", str(tag), rank=flags.RANK_MENTIONED)
        sink.mention(entity=tid, document=doc, role="tag", date=when)
    for place in fm.get("places") or []:
        sink.mention(surface=str(place), document=doc, role="place", date=when)


def _units() -> Iterator[Unit]:
    root = locations.site_articles()
    for path in sorted(root.glob("*.md")) if root.is_dir() else ():
        yield Unit(f"article:{path.stem}", file_digest(path), lambda sink, path=path: _emit(path, sink), date=path.stem[:10] if path.stem[:4].isdigit() else "",
                   path=rel(path, root.parent.parent))


def _watermark() -> str:
    root = locations.site_articles()
    return mark(root.glob("*.md")) if root.is_dir() else "none"


SOURCE = Source("articles", "articles", _units, _watermark)
