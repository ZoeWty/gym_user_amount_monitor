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


def fetch(url, client):
    resp = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def poll_once():
    """Fetch and store one sample for every venue. Returns rows written."""
    ts = datetime.now(timezone.utc)
    rows = []

    # ponytail: venues are fetched sequentially. At ~1s each this stays well
    # inside the 10-minute window up to ~100 venues; switch to asyncio.gather
    # with a semaphore if the list ever gets that long.
    with httpx.Client(verify=SSL_CONTEXT) as client:
        for venue in venue_config.load():
            try:
                payload = fetch(venue["url"], client)
            except Exception as exc:
                # Deliberately broad, and per-venue: one unreachable site must
                # not stop the others from being recorded. No retry -- the next
                # tick is 10 minutes away and hammering a free service is rude.
                log.error("venue=%s fetch failed: %s", venue["id"], exc)
                continue

            venue_rows = parse(payload)
            if not venue_rows:
                log.error(
                    "venue=%s no usable rows in %r -- writing nothing",
                    venue["id"], payload,
                )
                continue
            rows += [(venue["id"], a, ts, c, cap) for a, c, cap in venue_rows]
            log.info(
                "venue=%s %s", venue["id"],
                " ".join(f"{a}={c}/{cap}" for a, c, cap in venue_rows),
            )

    if not rows:
        log.error("nothing usable from any venue -- writing nothing")
        return 0

    with connect() as conn:
        conn.cursor().executemany(
            "INSERT INTO occupancy (venue, area, ts, current, capacity) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
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
    init_schema()

    if args.loop is None:
        poll_once()
        return
    while True:
        poll_once()
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
