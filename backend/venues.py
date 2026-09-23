"""Venue registry.

Venues live in a JSON file rather than in code so new ones can be added
without a rebuild -- and so the file can be mounted as a k8s ConfigMap.
Adding a venue is one entry; nothing else in the system needs to change.

All CYC sports centres expose the same endpoint shape, so a new venue is
found by probing:  curl -s https://<subdomain>.cyc.org.tw/api
"""
import json
import os
from pathlib import Path

VENUES_PATH = Path(
    os.environ.get("VENUES_PATH", Path(__file__).with_name("venues.json"))
)


def load():
    """Return [{'id', 'name', 'url'}, ...]. Raises if the config is unusable."""
    data = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{VENUES_PATH}: expected a non-empty list of venues")
    seen = set()
    for v in data:
        missing = {"id", "name", "url"} - v.keys()
        if missing:
            raise ValueError(f"{VENUES_PATH}: venue {v!r} is missing {missing}")
        if v["id"] in seen:
            raise ValueError(f"{VENUES_PATH}: duplicate venue id {v['id']!r}")
        seen.add(v["id"])
    return data


def ids():
    return [v["id"] for v in load()]


def default_id():
    return load()[0]["id"]
