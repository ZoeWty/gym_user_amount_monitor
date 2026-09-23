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


def _resolve_venue(venue):
    """Validate the venue id against the registry. Unknown id -> 404."""
    known = venue_config.ids()
    if venue is None:
        return known[0]
    if venue not in known:
        raise HTTPException(404, f"unknown venue {venue!r}; known: {known}")
    return venue


def _bucket(ts):
    """Floor a timestamp to its 10-minute bucket in Taipei local time."""
    local = ts.astimezone(TAIPEI)
    return local.replace(minute=local.minute // 10 * 10, second=0, microsecond=0)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/venues")
def list_venues():
    return [{"id": v["id"], "name": v["name"]} for v in venue_config.load()]


@app.get("/api/latest")
def latest(venue: str | None = Query(None)):
    """Most recent reading per area for one venue."""
    venue = _resolve_venue(venue)
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ON (area) area, ts, current, capacity "
            "FROM occupancy WHERE venue = %s ORDER BY area, ts DESC",
            (venue,),
        ).fetchall()
    return {
        "venue": venue,
        "fetched_at": max((r[1] for r in rows), default=None),
        "areas": {
            r[0]: {"current": r[2], "capacity": r[3], "ts": r[1]} for r in rows
        },
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
            "SELECT area, ts, current FROM occupancy "
            "WHERE venue = %s AND ts >= %s AND ts < %s",
            (venue, start, end),
        ).fetchall()

    seen = {(_bucket(ts), area): current for area, ts, current in rows}

    # Don't emit buckets that haven't happened yet -- a trailing run of nulls
    # for the rest of today is noise, not a gap.
    now = datetime.now(TAIPEI)
    stop = min(end, now + BUCKET) if start <= now < end else end

    points, b = [], start
    while b < stop:
        points.append(
            {"ts": b.isoformat(), **{a: seen.get((b, a)) for a in areas}}
        )
        b += BUCKET

    return {"venue": venue, "date": day.isoformat(), "areas": areas,
            "points": points}


# Mounted last so the /api and /healthz routes above take precedence.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
