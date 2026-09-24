"""Read-only HTTP API over the occupancy table, plus the built SPA.

Every endpoint is a GET and nothing here mutates state, which is what keeps
the public-facing blast radius small (see the design doc, §7).
"""
import os
from contextlib import asynccontextmanager
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

import venues as venue_config
from db import connect, init_schema

TAIPEI = ZoneInfo("Asia/Taipei")
BUCKET = timedelta(minutes=10)

# Opening hours, Taipei local. Outside these the centres are shut and upstream
# reports a literal 0, which is true but says nothing about how busy it gets --
# and 14 hours of flat zeros squash the part of the chart you actually read.
# Filtered on read, not on write: the rows stay in the table, so changing these
# hours (or dropping the filter) needs no backfill.
OPEN_TIME = time_cls(8, 0)
CLOSE_TIME = time_cls(22, 0)
OPEN_HOURS_SQL = "(ts AT TIME ZONE 'Asia/Taipei')::time BETWEEN %s AND %s"
STATIC_DIR = Path(
    os.environ.get(
        "STATIC_DIR", Path(__file__).resolve().parent.parent / "frontend" / "dist"
    )
)


@asynccontextmanager
async def lifespan(app):
    init_schema()
    yield


app = FastAPI(title="Gym Monitor", lifespan=lifespan)


def _known_venues():
    """[(id, name), ...] for venues that have data, newest name per venue.

    Read from the table rather than from config: the registry is upstream now,
    and a venue nobody has collected yet should not be selectable.
    """
    with connect() as conn:
        return conn.execute(
            # NULLS LAST matters: extra sources (文山's ice rink) write no
            # name and share the aggregate's timestamp, so without it the
            # nameless row can win and the venue shows up as its own id.
            "SELECT DISTINCT ON (venue) venue, name FROM occupancy "
            "ORDER BY venue, ts DESC, name NULLS LAST"
        ).fetchall()


def _resolve_venue(venue):
    """Validate the venue id against collected data. Unknown id -> 404."""
    known = [v for v, _ in _known_venues()]
    if not known:
        raise HTTPException(503, "no data collected yet")
    if venue is None:
        default = venue_config.load().get("default")
        return default if default in known else known[0]
    if venue not in known:
        raise HTTPException(404, f"unknown venue {venue!r}; known: {known}")
    return venue


def _bucket(ts):
    """Floor a timestamp to its 10-minute bucket in Taipei local time."""
    local = ts.astimezone(TAIPEI)
    return local.replace(minute=local.minute // 10 * 10, second=0, microsecond=0)


def drop_implausible(rows):
    """Drop readings upstream cannot actually mean. Rows are (area, ts, current, capacity).

    Two rules, both seen in real data on 2026-09-24:

    * `current > capacity` -- 北投 reported 974 then 996 swimmers against a
      capacity of 200, which looks like a running admission count rather than
      how many people are in the water.
    * a lone 0 while another area shares its timestamp and is busy -- 南港 swim
      read 17 -> 0 -> 31 in twenty minutes while the gym beside it held at ~35.
      Every area reading 0 at once is a genuinely empty venue, which happens at
      opening, and is kept.

    Parsing cannot catch either: both are valid integers. Applied on read, so
    the rows stay in the table and the rules can change without a backfill.
    """
    kept = [r for r in rows if r[3] is None or r[2] <= r[3]]
    busy_at = {r[1] for r in kept if r[2] > 0}
    return [r for r in kept if r[2] > 0 or r[1] not in busy_at]


def open_buckets(day, now):
    """The 10-minute buckets inside `day`'s opening hours, none later than now.

    Returns [] for a day that has not opened yet, and the full window for any
    day already past.
    """
    start = datetime.combine(day, OPEN_TIME, tzinfo=TAIPEI)
    end = datetime.combine(day, CLOSE_TIME, tzinfo=TAIPEI)
    last = end if now >= end else _bucket(now)

    out, b = [], start
    while b <= last:
        out.append(b)
        b += BUCKET
    return out


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/venues")
def list_venues():
    """Every venue with data: name, coordinates, and its latest reading.

    One query instead of twelve round trips -- the map needs all of them at
    once, and so will /api/recommend later.
    """
    cfg = venue_config.load()
    coords = cfg.get("coords", {})

    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ON (venue, area) venue, area, ts, current, capacity "
            "FROM occupancy WHERE " + OPEN_HOURS_SQL +
            " ORDER BY venue, area, ts DESC",
            (OPEN_TIME, CLOSE_TIME),
        ).fetchall()

    # Filter per venue, never across venues. drop_implausible groups by
    # timestamp, and every venue shares a poll cycle's timestamp -- run it on
    # the whole set and a busy gym at 南港 would vouch for a 0 at 信義.
    per_venue = {}
    for venue, area, ts, current, capacity in rows:
        per_venue.setdefault(venue, []).append((area, ts, current, capacity))

    out = []
    for venue, name in _known_venues():
        lat_lon = coords.get(venue)
        out.append({
            "id": venue,
            "name": name or venue,
            "lat": lat_lon[0] if lat_lon else None,
            "lon": lat_lon[1] if lat_lon else None,
            "areas": {
                a: {"current": c, "capacity": cap}
                for a, _ts, c, cap in drop_implausible(per_venue.get(venue, []))
            },
        })

    default = cfg.get("default")
    out.sort(key=lambda r: (r["id"] != default, r["id"]))
    return out


@app.get("/api/latest")
def latest(venue: str | None = Query(None)):
    """Most recent reading per area for one venue."""
    venue = _resolve_venue(venue)
    with connect() as conn:
        # Not DISTINCT ON: the glitch filter needs the siblings at each
        # timestamp, so take a short window and pick the newest per area here.
        # ponytail: 30 rows ~= 10 polls across 3 areas. If a venue ever
        # reports more areas, raise it or switch to a window function.
        rows = conn.execute(
            "SELECT area, ts, current, capacity FROM occupancy "
            "WHERE venue = %s AND " + OPEN_HOURS_SQL +
            " ORDER BY ts DESC LIMIT 30",
            (venue, OPEN_TIME, CLOSE_TIME),
        ).fetchall()

    newest = {}
    for area, ts, current, capacity in drop_implausible(rows):
        newest.setdefault(area, {"current": current, "capacity": capacity, "ts": ts})
    # Sorted so the cards keep a stable order; the rows arrive newest-first,
    # which says nothing about area order.
    areas = {a: newest[a] for a in sorted(newest)}
    return {
        "venue": venue,
        "fetched_at": max((a["ts"] for a in areas.values()), default=None),
        "areas": areas,
    }


@app.get("/api/series")
def series(venue: str | None = Query(None), date: str | None = Query(None)):
    """One day of 10-minute buckets for one venue, in wide format.

    Buckets with no reading come back as null rather than being omitted, so
    the chart can draw a real gap instead of inventing a straight line across
    hours when nothing was collected.
    """
    venue = _resolve_venue(venue)

    # `date` arrives from the public internet: parse strictly, and only ever
    # reach the database through bound parameters.
    if date is None:
        day = datetime.now(TAIPEI).date()
    else:
        try:
            day = date_cls.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, f"date must be YYYY-MM-DD, got {date!r}")

    start = datetime.combine(day, time_cls.min, tzinfo=TAIPEI)
    end = start + timedelta(days=1)

    with connect() as conn:
        areas = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT area FROM occupancy WHERE venue = %s "
                "ORDER BY area",
                (venue,),
            ).fetchall()
        ]
        rows = conn.execute(
            "SELECT area, ts, current, capacity FROM occupancy "
            "WHERE venue = %s AND ts >= %s AND ts < %s AND " + OPEN_HOURS_SQL,
            (venue, start, end, OPEN_TIME, CLOSE_TIME),
        ).fetchall()

    seen = {
        (_bucket(ts), area): current
        for area, ts, current, _cap in drop_implausible(rows)
    }

    points = [
        {"ts": b.isoformat(), **{a: seen.get((b, a)) for a in areas}}
        for b in open_buckets(day, datetime.now(TAIPEI))
    ]
    return {
        "venue": venue,
        "date": day.isoformat(),
        "areas": areas,
        "open_from": OPEN_TIME.isoformat(timespec="minutes"),
        "open_to": CLOSE_TIME.isoformat(timespec="minutes"),
        "points": points,
    }


# Mounted last so the /api and /healthz routes above take precedence.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
