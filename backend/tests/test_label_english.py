"""English-first t0 menu labels."""

from __future__ import annotations

from algent_backend.data_ingestion.newsroom.discovery.label_english import (
    format_menu_label,
    looks_non_english,
)


def test_looks_non_english_scripts() -> None:
    assert looks_non_english("На Западе раскрыли удар")
    assert looks_non_english("不知悔改 菲防长公然宣称")
    assert looks_non_english("רק דוגמה בעברית")
    assert not looks_non_english("Trump holds off strikes on Iran")


def test_format_menu_label_shows_en_and_original() -> None:
    item = {
        "label": "На Западе раскрыли удар",
        "signals": {"label_en": "The West revealed the blow Finland took"},
    }
    display, original = format_menu_label(item)
    assert display.startswith("The West")
    assert original and "На Западе" in original


def test_format_menu_label_english_passthrough() -> None:
    display, original = format_menu_label({"label": "Trump holds off strikes", "signals": {}})
    assert display == "Trump holds off strikes"
    assert original is None
