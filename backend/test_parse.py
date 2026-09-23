"""Checks for the branching logic: payload parsing and venue config validation.

The rule that matters most is that a malformed or degraded upstream response
produces NO rows -- never a row with 0 in it.

Run directly (python test_parse.py) or under pytest.
"""
import json
import tempfile
from pathlib import Path

import pytest

import venues as venue_config
from poll import parse


# --- payload parsing -------------------------------------------------------

def test_normal_payload():
    assert parse({"gym": ["48", "100", "0"], "swim": ["73", "200", "0"]}) == [
        ("gym", 48, 100),
        ("swim", 73, 200),
    ]


def test_resource_not_found_is_dropped_not_zeroed():
    rows = parse({"gym": ["找不到資源，請稍後再試", "100", "0"]})
    assert rows == [], f"error string must yield no rows, got {rows}"


def test_empty_list_payload():
    assert parse([]) == []


def test_non_numeric_is_dropped():
    assert parse({"gym": ["N/A", "100"]}) == []
    assert parse({"gym": ["48", ""]}) == []
    assert parse({"gym": [None, None]}) == []


def test_short_and_malformed_shapes():
    assert parse({"gym": ["48"]}) == []
    assert parse({"gym": "48"}) == []
    assert parse({"gym": None}) == []


def test_one_bad_area_does_not_drop_the_good_one():
    assert parse({"gym": ["48", "100"], "swim": ["找不到資源", "200"]}) == [
        ("gym", 48, 100)
    ]


def test_ice_rink_is_kept():
    # 文山 reports an ice rink; the long-format schema takes it with no DDL.
    assert parse({"gym": ["29", "110", "0"], "ice": ["17", "120", "0"]}) == [
        ("gym", 29, 110),
        ("ice", 17, 120),
    ]


# --- venue config ----------------------------------------------------------

def _with_venues(monkeypatch, data):
    path = Path(tempfile.mkdtemp()) / "venues.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(venue_config, "VENUES_PATH", path)


def test_shipped_config_is_valid():
    assert len(venue_config.load()) >= 1
    assert venue_config.default_id() == venue_config.ids()[0]


def test_duplicate_venue_id_is_rejected(monkeypatch):
    _with_venues(monkeypatch, [
        {"id": "a", "name": "A", "url": "http://a"},
        {"id": "a", "name": "A2", "url": "http://a2"},
    ])
    with pytest.raises(ValueError, match="duplicate"):
        venue_config.load()


def test_missing_field_is_rejected(monkeypatch):
    _with_venues(monkeypatch, [{"id": "a", "name": "A"}])
    with pytest.raises(ValueError, match="missing"):
        venue_config.load()


def test_empty_config_is_rejected(monkeypatch):
    _with_venues(monkeypatch, [])
    with pytest.raises(ValueError):
        venue_config.load()
