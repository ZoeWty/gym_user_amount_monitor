"""Fetch current occupancy for every configured venue and record it.

Runs once and exits by default, so the same file works as a manual command,
as a Compose service (--loop 600), and as a k8s CronJob (no flag). Scheduling
belongs to the environment, not to a library in here.
"""
import argparse
import logging
import ssl
import time
from datetime import datetime, timezone

import httpx

import venues as venue_config
from db import connect, init_schema

USER_AGENT = "gym-monitor/1.0 (personal occupancy logger)"
TIMEOUT = 10.0


def _ssl_context():
    """TLS settings for the upstream sports-centre sites.

    Their certificates chain through "TWCA Secure SSL Certification Authority",
    whose CA certificate omits the Subject Key Identifier extension that
    RFC 5280 requires. Python 3.13+ enables VERIFY_X509_STRICT in
    create_default_context(), which rejects that chain outright -- on Linux as
    well as macOS, so this is not a local quirk.

    Only that one conformance check is dropped. Chain building, expiry and
    hostname verification all stay on; this is deliberately NOT verify=False.
    Revisit if the sites ever fix their chain.
    """
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


SSL_CONTEXT = _ssl_context()

log = logging.getLogger("poll")


def parse(payload):
    """Turn one venue's payload into [(area, current, capacity), ...].

    Upstream normally returns {"gym": ["48", "100", "0"], ...} but degrades to
    an error string ("找不到資源…") or a bare [] when a venue has no live data
    -- the site's own JS checks for exactly that.

    Anything that does not parse as an integer is DROPPED, never recorded as 0.
    A stored 0 would be indistinguishable from "the gym is genuinely empty" on
    the chart, and wrong data is worse than missing data.
    """
    if not isinstance(payload, dict):
        log.warning("payload is not an object: %r", payload)
        return []
    rows = []
    for area, values in payload.items():
        if not isinstance(values, (list, tuple)) or len(values) < 2:
            log.warning("area=%s unexpected shape: %r", area, values)
            continue
        try:
            current, capacity = int(values[0]), int(values[1])
        except (TypeError, ValueError):
            log.warning("area=%s non-numeric: %r", area, list(values[:2]))
            continue
        rows.append((area, current, capacity))
    return rows


AGGREGATE_FIELDS = (
    ("gym", "gymPeopleNum", "gymMaxPeopleNum"),
    ("swim", "swPeopleNum", "swMaxPeopleNum"),
)


def parse_aggregate(payload):
    """Turn the all-venues payload into [(venue, name, area, cur, cap), ...].

    Same rule as parse(): anything that will not convert to an integer is
    dropped rather than recorded as 0.
    """
    if not isinstance(payload, dict):
        log.warning("aggregate payload is not an object: %r", payload)
        return []
    rows = []
    for v in payload.get("locationPeopleNums") or []:
        if not isinstance(v, dict) or not v.get("LID"):
            log.warning("aggregate entry has no LID: %r", v)
            continue
        venue = str(v["LID"]).lower()
        name = v.get("lidName") or venue
        for area, cur_key, cap_key in AGGREGATE_FIELDS:
            try:
                current, capacity = int(v[cur_key]), int(v[cap_key])
            except (KeyError, TypeError, ValueError):
                log.warning("venue=%s area=%s unusable: %r", venue, area, v)
                continue
            rows.append((venue, name, area, current, capacity))
    return rows


def fetch(url, client, post=False):
    # The aggregate endpoint answers 411 without a Content-Length, so the POST
    # needs an explicit (empty) body.
    resp = (
        client.post(url, content=b"", headers={"User-Agent": USER_AGENT},
                    timeout=TIMEOUT)
        if post else
        client.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    )
    resp.raise_for_status()
    return resp.json()


def poll_once():
    """Fetch and store one sample for every venue. Returns rows written."""
    ts = datetime.now(timezone.utc)
    cfg = venue_config.load()
    rows = []

    with httpx.Client(verify=SSL_CONTEXT) as client:
        # One call covers all twelve venues. Each source gets its own guard:
        # the aggregate failing costs every venue's gym and pool, an extra
        # source failing costs only that venue's extra areas.
        try:
            for venue, name, area, cur, cap in parse_aggregate(
                fetch(cfg["aggregate"], client, post=True)
            ):
                rows.append((venue, name, area, ts, cur, cap))
        except Exception as exc:
            # No retry -- the next tick is 10 minutes away and hammering a free
            # service is rude.
            log.error("aggregate fetch failed: %s", exc)

        for src in cfg.get("extra", []):
            try:
                payload = fetch(src["url"], client)
            except Exception as exc:
                log.error("venue=%s extra fetch failed: %s", src["venue"], exc)
                continue
            wanted = set(src["areas"])
            # Take only the declared areas. This source also reports gym and
            # swim, and storing those would duplicate the aggregate's rows.
            extra = [r for r in parse(payload) if r[0] in wanted]
            if not extra:
                log.error("venue=%s no usable extra areas in %r",
                          src["venue"], payload)
                continue
            rows += [(src["venue"], None, a, ts, c, cap) for a, c, cap in extra]

    if rows:
        by_venue = {}
        for venue, _name, area, _ts, cur, cap in rows:
            by_venue.setdefault(venue, []).append(f"{area}={cur}/{cap}")
        log.info("%d venues: %s", len(by_venue),
                 "  ".join(f"{v} {' '.join(a)}" for v, a in sorted(by_venue.items())))

    if not rows:
        log.error("nothing usable from any source -- writing nothing")
        return 0

    with connect() as conn:
        conn.cursor().executemany(
            "INSERT INTO occupancy (venue, name, area, ts, current, capacity) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            rows,
        )
    log.info("stored %d rows", len(rows))
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--loop", type=int, metavar="SECONDS",
        help="keep polling every SECONDS (for local/Compose use; "
             "omit under a k8s CronJob)",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    if args.loop is None:
        init_schema()
        poll_once()
        return

    while True:
        try:
            # Inside the guard, and every cycle: CREATE TABLE IF NOT EXISTS is
            # cheap and idempotent, and running it here means the poller heals
            # itself once the database comes back instead of having died at
            # startup because it was not up yet.
            init_schema()
            wrote = poll_once()
        except Exception:
            # The loop has to outlive any single failure. poll_once() guards
            # the fetch but not the database write, so a Postgres blip -- which
            # is exactly what a laptop resuming from sleep produces -- would
            # otherwise escape, end the loop and stop collection silently.
            log.exception("poll cycle failed")
            wrote = 0

        # A cycle that stored nothing is usually a transient (DNS not back up
        # yet after a resume), so come back in a minute instead of losing the
        # whole interval.
        # ponytail: flat 60s, no exponential backoff. Even in a sustained
        # outage that is one request per venue per minute -- still lighter
        # than the upstream site's own page, which polls every 60s per tab.
        time.sleep(60 if wrote == 0 else args.loop)


if __name__ == "__main__":
    main()
