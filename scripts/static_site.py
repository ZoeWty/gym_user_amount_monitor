"""Generate the static data the GitHub Pages site reads.

GitHub Pages serves files, nothing else -- no FastAPI, no Postgres, no poller.
So the same payloads are written out as files, and `history.jsonl` takes the
database's place as the store.

Three commands, because they run in different places:

    seed     Postgres -> history.jsonl      (once, on your machine)
    collect  upstream -> history.jsonl      (every run, in GitHub Actions)
    build    history.jsonl -> docs/data/    (after either of the above)

Actions cannot reach a Postgres on your laptop, which is why `collect` goes
straight to the upstream API instead. `seed` is how the three weeks already in
Postgres get in.

Run from the repo root:  python scripts/static_site.py build
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

HISTORY = ROOT / "docs" / "data" / "history.jsonl"
OUT = ROOT / "docs" / "data"

# Only regenerate this many days of series files. Past days never change, so
# re-emitting all of them would churn hundreds of files in git on every run.
# ponytail: 14 days. Raise it when the dashboard offers a longer range.
KEEP_DAYS = 14


def _load():
    if not HISTORY.exists():
        return []
    return [json.loads(line) for line in HISTORY.read_text().splitlines() if line.strip()]


def _write(rows):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    # Deduplicate on the same key the database uses, so re-running seed or a
    # double-fired cron cannot produce two readings for one moment.
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["ts"]):
        key = (r["venue"], r["area"], r["ts"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    HISTORY.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    return len(out)


def seed():
    """Copy everything in Postgres into history.jsonl."""
    from db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT venue, name, area, ts, current, capacity FROM occupancy"
        ).fetchall()
    total = _write(_load() + [
        {"venue": v, "name": n, "area": a, "ts": ts.isoformat(),
         "current": c, "capacity": cap}
        for v, n, a, ts, c, cap in rows
    ])
    print(f"seeded from Postgres: {len(rows)} rows read, {total} in history")


def collect():
    """Fetch the upstream API once and append whatever it reports."""
    import httpx

    import venues as venue_config
    from poll import SSL_CONTEXT, USER_AGENT, parse, parse_aggregate

    cfg = venue_config.load()
    ts = datetime.now(timezone.utc).isoformat()
    new = []

    with httpx.Client(verify=SSL_CONTEXT, timeout=20) as client:
        r = client.post(cfg["aggregate"], content=b"", headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        for venue, name, area, cur, cap in parse_aggregate(r.json()):
            new.append({"venue": venue, "name": name, "area": area, "ts": ts,
                        "current": cur, "capacity": cap})

        for src in cfg.get("extra", []):
            try:
                r = client.get(src["url"], headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
                wanted = set(src["areas"])
                for area, cur, cap in parse(r.json()):
                    if area in wanted:
                        new.append({"venue": src["venue"], "name": None, "area": area,
                                    "ts": ts, "current": cur, "capacity": cap})
            except Exception as exc:
                # One extra source failing must not lose the other twelve venues.
                print(f"extra source {src['venue']} failed: {exc}", file=sys.stderr)

    if not new:
        print("nothing usable from upstream -- writing nothing")
        return
    total = _write(_load() + new)
    print(f"collected {len(new)} readings, {total} in history")


def build():
    """Turn history.jsonl into the files the frontend fetches."""
    from main import TAIPEI, drop_implausible, open_buckets, _bucket

    rows = _load()
    if not rows:
        print("history.jsonl is empty -- run seed or collect first")
        return

    by_venue = defaultdict(list)
    names = {}
    for r in rows:
        ts = datetime.fromisoformat(r["ts"])
        by_venue[r["venue"]].append((r["area"], ts, r["current"], r["capacity"]))
        if r.get("name"):
            names[r["venue"]] = r["name"]

    coords = json.loads((ROOT / "backend" / "venues.json").read_text())["coords"]
    today = datetime.now(TAIPEI).date()
    recent = {today.fromordinal(today.toordinal() - i) for i in range(KEEP_DAYS)}

    venues_out, written = [], 0
    for venue, entries in sorted(by_venue.items()):
        kept = drop_implausible(entries)
        newest_ts = max(ts for _a, ts, _c, _cap in kept) if kept else None
        latest_areas = {}
        for area, ts, cur, cap in sorted(kept, key=lambda e: e[1], reverse=True):
            latest_areas.setdefault(area, {"current": cur, "capacity": cap,
                                           "ts": ts.isoformat()})

        lat_lon = coords.get(venue)
        venues_out.append({
            "id": venue, "name": names.get(venue, venue),
            "lat": lat_lon[0] if lat_lon else None,
            "lon": lat_lon[1] if lat_lon else None,
            "areas": {a: {"current": v["current"], "capacity": v["capacity"]}
                      for a, v in latest_areas.items()},
        })

        _dump(OUT / "latest" / f"{venue}.json", {
            "venue": venue,
            "fetched_at": newest_ts.isoformat() if newest_ts else None,
            "areas": latest_areas,
        })
        written += 1

        # Group into days, then emit only the recent ones: a past day's file
        # can never change, so rewriting it only churns git.
        per_day = defaultdict(list)
        for area, ts, cur, cap in kept:
            per_day[ts.astimezone(TAIPEI).date()].append((area, ts, cur, cap))

        areas_seen = sorted({a for a, _t, _c, _cap in kept})
        for day, day_rows in per_day.items():
            if day not in recent:
                continue
            seen = {(_bucket(ts), a): c for a, ts, c, _cap in day_rows}
            points = [
                {"ts": b.isoformat(), **{a: seen.get((b, a)) for a in areas_seen}}
                for b in open_buckets(day, datetime.now(TAIPEI))
            ]
            _dump(OUT / "series" / venue / f"{day.isoformat()}.json", {
                "venue": venue, "date": day.isoformat(), "areas": areas_seen,
                "open_from": "08:00", "open_to": "22:00", "points": points,
            })
            written += 1

    default = json.loads((ROOT / "backend" / "venues.json").read_text()).get("default")
    venues_out.sort(key=lambda r: (r["id"] != default, r["id"]))
    _dump(OUT / "venues.json", venues_out)

    print(f"built {written + 1} files for {len(venues_out)} venues "
          f"from {len(rows)} readings")


def _dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in {"seed", "collect", "build"}:
        sys.exit(__doc__)
    globals()[cmd]()
