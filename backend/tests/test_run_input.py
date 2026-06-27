"""Tests for run-input parsing — the 'enter at any stage' injection plumbing."""

from __future__ import annotations

import json

import pytest

from algent_backend.cli.runs._shared import parse_input_arg


def test_input_file_mounted_under_key(tmp_path) -> None:
    f = tmp_path / "pool.json"
    f.write_text(json.dumps({"item_count": 3, "items": []}), encoding="utf-8")
    out = parse_input_arg(None, None, input_file=str(f), input_key="pool")
    assert out == {"pool": {"item_count": 3, "items": []}}  # mounted under the state key


def test_input_file_as_whole_dict_then_flags_merge(tmp_path) -> None:
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"pool": {"a": 1}}), encoding="utf-8")
    out = parse_input_arg('{"extra": true}', "T", input_file=str(f))
    assert out == {"pool": {"a": 1}, "extra": True, "topic": "T"}  # file is the dict; flags merge on top


def test_input_file_non_object_without_key_errors(tmp_path) -> None:
    f = tmp_path / "arr.json"
    f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a JSON object"):
        parse_input_arg(None, None, input_file=str(f))


def test_no_input_is_empty() -> None:
    assert parse_input_arg(None, None) == {}
