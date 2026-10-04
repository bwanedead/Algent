"""Wikimedia Commons sourcing — licence filter, metadata cleaning, credit line. No network."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import real_images


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._p, self.status_code, self.content = payload, 200, b""

    def json(self) -> dict:
        return self._p


def _page(i: int, title: str, lic: str, width: int = 2000, mime: str = "image/jpeg") -> dict:
    return {"index": i, "title": f"File:{title}", "imageinfo": [{
        "width": width, "mime": mime, "thumburl": f"https://t/{i}.jpg",
        "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{i}",
        "extmetadata": {
            "LicenseShortName": {"value": lic},
            "Artist": {"value": '<a href="//x">Jane &amp; Co</a>'},
            "ImageDescription": {"value": "<b>The strait</b> at dusk"},
            "DateTimeOriginal": {"value": "2020-03-24 05:02:59"},
        }}]}


class _Http:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages

    def get(self, *_a, **_k) -> _Resp:
        return _Resp({"query": {"pages": self.pages}})


def test_only_reusable_usable_files_survive() -> None:
    http = _Http([
        _page(2, "b.jpg", "CC BY-SA 4.0"),
        _page(1, "a.jpg", "Public domain"),
        _page(3, "nc.jpg", "CC BY-NC 2.0"),
        _page(4, "tiny.jpg", "CC0", width=300),
        _page(5, "vector.svg", "CC0", mime="image/svg+xml"),
        _page(6, "blank.jpg", ""),
    ])
    got = real_images.search_commons("Strait of Hormuz", http=http)
    assert [c.title for c in got] == ["a.jpg", "b.jpg"]          # search rank order kept
    assert got[0].artist == "Jane & Co" and got[0].description == "The strait at dusk"


def test_no_network_is_no_photo() -> None:
    class _Down:
        def get(self, *_a, **_k):
            raise OSError("offline")
    assert real_images.search_commons("x", http=_Down()) == []


def test_credit_names_author_source_licence_and_year() -> None:
    c = real_images.search_commons("x", http=_Http([_page(1, "a.jpg", "CC BY-SA 4.0")]))[0]
    line = real_images.credit_line(c)
    assert line.startswith("*Photo: Jane & Co") and line.endswith("*")
    assert "[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:1)" in line
    assert "CC BY-SA 4.0" in line and "2020" in line
