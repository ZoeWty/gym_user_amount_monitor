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


# --- source registry ------------------------------------------------------

def _with_config(monkeypatch, data):
    path = Path(tempfile.mkdtemp()) / "venues.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(venue_config, "VENUES_PATH", path)


def test_shipped_config_is_valid():
    cfg = venue_config.load()
    assert cfg["aggregate"].startswith("https://")


def test_extra_source_claiming_an_aggregate_area_is_rejected(monkeypatch):
    # the whole point of the check: this would store 文山 gym twice per poll
    _with_config(monkeypatch, {"aggregate": "https://x", "extra": [
        {"venue": "wssc", "url": "https://y", "areas": ["ice", "gym"]}]})
    with pytest.raises(ValueError, match="already provides"):
        venue_config.load()


def test_extra_source_with_only_its_own_areas_is_fine(monkeypatch):
    _with_config(monkeypatch, {"aggregate": "https://x", "extra": [
        {"venue": "wssc", "url": "https://y", "areas": ["ice"]}]})
    assert venue_config.load()["extra"][0]["areas"] == ["ice"]


def test_missing_aggregate_is_rejected(monkeypatch):
    _with_config(monkeypatch, {"extra": []})
    with pytest.raises(ValueError, match="aggregate"):
        venue_config.load()


def test_extra_source_missing_a_field_is_rejected(monkeypatch):
    _with_config(monkeypatch, {"aggregate": "https://x",
                               "extra": [{"venue": "wssc"}]})
    with pytest.raises(ValueError, match="missing"):
        venue_config.load()


# --- aggregate parsing ----------------------------------------------------

from poll import parse_aggregate

_AGG = {"locationPeopleNums": [
    {"LID": "NGSC", "lidName": "南港", "gymPeopleNum": "52",
     "gymMaxPeopleNum": "100", "swPeopleNum": "109", "swMaxPeopleNum": "200"},
]}


def test_aggregate_normal():
    assert parse_aggregate(_AGG) == [
        ("ngsc", "南港", "gym", 52, 100),
        ("ngsc", "南港", "swim", 109, 200),
    ]


def test_aggregate_lid_is_lowercased_into_the_venue_id():
    # 中山 is zssc here and nowhere cssc -- one id per building
    z = {"locationPeopleNums": [dict(_AGG["locationPeopleNums"][0], LID="ZSSC")]}
    assert {r[0] for r in parse_aggregate(z)} == {"zssc"}


def test_aggregate_non_numeric_area_is_dropped_not_zeroed():
    bad = {"locationPeopleNums": [
        dict(_AGG["locationPeopleNums"][0], swPeopleNum="找不到資源")]}
    assert [r[2] for r in parse_aggregate(bad)] == ["gym"]


def test_aggregate_entry_without_lid_is_skipped():
    assert parse_aggregate({"locationPeopleNums": [{"gymPeopleNum": "1"}]}) == []


def test_aggregate_empty_and_malformed():
    assert parse_aggregate({"locationPeopleNums": []}) == []
    assert parse_aggregate({}) == []
    assert parse_aggregate([]) == []


def test_aggregate_falls_back_to_the_id_when_unnamed():
    n = {"locationPeopleNums": [
        {k: v for k, v in _AGG["locationPeopleNums"][0].items() if k != "lidName"}]}
    assert parse_aggregate(n)[0][1] == "ngsc"


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


# --- implausible readings -------------------------------------------------

from main import drop_implausible

_T1, _T2 = "ts1", "ts2"


def test_over_capacity_is_dropped():
    # 北投 reported 974 swimmers against a capacity of 200
    rows = [("gym", _T1, 32, 60), ("swim", _T1, 974, 200)]
    assert drop_implausible(rows) == [("gym", _T1, 32, 60)]


def test_exactly_at_capacity_is_kept():
    rows = [("gym", _T1, 60, 60)]
    assert drop_implausible(rows) == rows


def test_lone_zero_next_to_a_busy_area_is_dropped():
    rows = [("gym", _T1, 35, 100), ("swim", _T1, 0, 200)]
    assert drop_implausible(rows) == [("gym", _T1, 35, 100)]


def test_all_areas_zero_is_kept():
    rows = [("gym", _T1, 0, 100), ("swim", _T1, 0, 200)]
    assert drop_implausible(rows) == rows


def test_zero_is_judged_per_timestamp_not_globally():
    rows = [("gym", _T1, 0, 100), ("swim", _T1, 0, 200),
            ("gym", _T2, 35, 100), ("swim", _T2, 0, 200)]
    assert drop_implausible(rows) == [
        ("gym", _T1, 0, 100), ("swim", _T1, 0, 200), ("gym", _T2, 35, 100)]


def test_an_over_capacity_sibling_does_not_rescue_a_zero():
    # the impossible row is removed first, so the 0 is no longer "next to busy"
    rows = [("gym", _T1, 974, 200), ("swim", _T1, 0, 200)]
    assert drop_implausible(rows) == [("swim", _T1, 0, 200)]


def test_null_capacity_skips_the_capacity_rule():
    # rows written before the name/capacity columns settled
    rows = [("gym", _T1, 35, None)]
    assert drop_implausible(rows) == rows


def test_nonzero_rows_are_never_touched():
    rows = [("gym", _T1, 35, 100), ("swim", _T1, 17, 200)]
    assert drop_implausible(rows) == rows


def test_empty_input():
    assert drop_implausible([]) == []
