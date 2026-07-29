#!/usr/bin/env python3
"""
Standalone Beat liveness healthcheck, used by the `beat` service's
docker-compose HEALTHCHECK.

Beat has no HTTP server of its own (that's Gunicorn's job, in the `web`
service), so this connects directly to Postgres and checks that
`beatTime.updatedAt` isn't stale -- the same signal as
src/controller/beatTimeController.py::is_beat_healthy /
GET /health/beatStatus, but standalone (no Flask app boot, no gunicorn
dependency) so it's cheap enough to run every few seconds.

Exit 0 = healthy, exit 1 = unhealthy/stale/unreachable.
"""
import os
import sys
from datetime import datetime, timedelta

import psycopg2


def main() -> int:
    postgres_url = os.environ.get("POSTGRES_URL")
    if not postgres_url:
        print("beat healthcheck: POSTGRES_URL not set")
        return 1

    schema = os.environ.get("SCHEMA_NAME", "erp_celery_poc")
    # Same staleness window used by BeatTimeController.is_beat_healthy.
    stale_after_seconds = int(os.environ.get("DB_WRITE_TASK_INTERVAL_SECONDS", 15)) * 3

    try:
        conn = psycopg2.connect(postgres_url, connect_timeout=5)
    except Exception as e:
        print(f"beat healthcheck: could not connect to Postgres: {e}")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT "updatedAt" FROM {schema}."beatTime" ORDER BY "updatedAt" DESC LIMIT 1')
            row = cur.fetchone()
    except Exception as e:
        print(f"beat healthcheck: query failed: {e}")
        return 1
    finally:
        conn.close()

    if row is None:
        print("beat healthcheck: no beatTime row yet (beat may still be starting up)")
        return 1

    last_beat = row[0]
    age = datetime.now() - last_beat
    if age > timedelta(seconds=stale_after_seconds):
        print(f"beat healthcheck: STALE -- last beat {age.total_seconds():.0f}s ago (limit {stale_after_seconds}s)")
        return 1

    print(f"beat healthcheck: ok -- last beat {age.total_seconds():.0f}s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
