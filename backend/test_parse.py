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


# --- opening hours ---------------------------------------------------------

from datetime import date as _date, datetime as _dt
from zoneinfo import ZoneInfo as _ZI

from main import CLOSE_TIME, OPEN_TIME, TAIPEI, open_buckets

_DAY = _date(2026, 9, 24)


def _at(h, m=0):
    return _dt(2026, 9, 24, h, m, tzinfo=TAIPEI)


def test_past_day_is_the_whole_window():
    b = open_buckets(_DAY, _at(23, 30))
    assert b[0].time() == OPEN_TIME
    assert b[-1].time() == CLOSE_TIME
    assert len(b) == 85                      # 08:00..22:00 inclusive, /10min


def test_nothing_outside_the_window_leaks_in():
    for b in open_buckets(_DAY, _at(23, 30)):
        assert OPEN_TIME <= b.time() <= CLOSE_TIME


def test_before_opening_yields_nothing():
    assert open_buckets(_DAY, _at(7, 59)) == []


def test_exactly_at_opening_yields_one_bucket():
    assert [b.time() for b in open_buckets(_DAY, _at(8, 0))] == [OPEN_TIME]


def test_midday_stops_at_the_current_bucket():
    b = open_buckets(_DAY, _at(15, 7))
    assert b[-1].time().hour == 15 and b[-1].time().minute == 0   # not 15:10


def test_after_closing_does_not_run_past_close():
    assert open_buckets(_DAY, _at(23, 0))[-1].time() == CLOSE_TIME


def test_browser_in_another_timezone_still_gets_taipei_hours():
    # now expressed in UTC must not shift the window
    utc_now = _dt(2026, 9, 24, 7, 0, tzinfo=_ZI("UTC"))   # = 15:00 Taipei
    b = open_buckets(_DAY, utc_now)
    assert b[0].time() == OPEN_TIME
    assert b[-1].time().hour == 15
