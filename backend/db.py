"""Database connection and schema.

One table, so the schema lives here and is applied on startup with
CREATE TABLE IF NOT EXISTS. Introduce Alembic at the second schema change.
"""
import os

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://gym:gym@localhost:5432/gym"
)

# Long format -- one row per (venue, area) per poll -- rather than a wide table.
# Same amount of code, and it absorbs both new venues and venues with a
# different mix of facilities (文山 also reports an ice rink) without DDL.
#
# PK order is (venue, area, ts), not (ts, venue, area): every read filters on a
# single venue and then scans a time range, so venue must lead for the index to
# do the work. It also makes writes idempotent -- a double-fired k8s CronJob or
# a manual backfill cannot create duplicate points.
DDL = """
CREATE TABLE IF NOT EXISTS occupancy (
    venue     text        NOT NULL,
    area      text        NOT NULL,
    ts        timestamptz NOT NULL,
    current   integer     NOT NULL,
    capacity  integer     NOT NULL,
    PRIMARY KEY (venue, area, ts)
);
"""


def connect():
    """Open a connection. Used per-request; at ~0 QPS a pool buys nothing."""
    return psycopg.connect(DATABASE_URL)


def init_schema():
    with connect() as conn:
        conn.execute(DDL)
