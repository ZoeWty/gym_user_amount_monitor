"""Source registry.

There is no list of venues here. The aggregate endpoint returns all twelve
Taipei sports centres with their ids and names, so the registry is upstream
and cannot drift from it. That also means one id namespace: 中山 is `zssc`
and only `zssc`, where a hand-kept list would eventually gain `cssc` (its CYC
subdomain) as a second id for the same building.

`extra` covers what the aggregate does not carry. It has exactly one entry
today -- the aggregate has no ice rink, so 文山's rink comes from CYC.
"""
import json
import os
from pathlib import Path

VENUES_PATH = Path(
    os.environ.get("VENUES_PATH", Path(__file__).with_name("venues.json"))
)

# The aggregate response has fixed gym/swim fields, so these are the areas it
# can ever produce. An `extra` source claiming one of them would write a second
# row for the same (venue, area) at a slightly different timestamp, which the
# (venue, area, ts) primary key does not catch.
AGGREGATE_AREAS = frozenset({"gym", "swim"})


def load():
    """Return the config dict. Raises if it would produce duplicate rows."""
    cfg = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or not cfg.get("aggregate"):
        raise ValueError(f"{VENUES_PATH}: missing 'aggregate' URL")

    for src in cfg.get("extra", []):
        missing = {"venue", "url", "areas"} - src.keys()
        if missing:
            raise ValueError(f"{VENUES_PATH}: extra source {src!r} missing {missing}")
        clash = AGGREGATE_AREAS & set(src["areas"])
        if clash:
            raise ValueError(
                f"{VENUES_PATH}: extra source for {src['venue']!r} claims "
                f"{sorted(clash)}, which the aggregate already provides -- "
                f"that would store the same reading twice"
            )
    return cfg
