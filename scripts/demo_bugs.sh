#!/bin/bash
# Manual walkthrough of the bug reproduction / fix verification steps used
# during development of this POC. This is not a fully unattended script
# (it prints instructions and pauses at the interesting points) --
# see the README for the exact commands and expected before/after output.
#
# Prereqs: `docker compose up -d --build` (brings up postgres, web, beat,
# worker -- see "Process topology" in README.md for why web/beat/worker
# are three separate services).
#
# Part 1 -- BUG #1 (CustomScheduler.apply_entry has no try/except):
#   1. docker compose up -d beat
#   2. Drop the beatTime table to force the health-check query to fail:
#        docker compose exec postgres psql -U postgres -d erp_celery_poc \
#          -c 'DROP TABLE erp_celery_poc."beatTime";'
#   3. UNFIXED (temporarily remove the try/except in
#      src/config/scheduleTasks.py, rebuild `beat`): `docker compose logs
#      beat` shows "beat raised exception ... CRITICAL" and the beat
#      process dies; `docker inspect erp-celery-poc-beat-1 --format
#      '{{.RestartCount}}'` increments -- ONLY the `beat` container
#      restarts, `web`/`worker` are unaffected.
#   4. FIXED (current code): `docker compose logs beat` shows
#        "CustomScheduler.apply_entry: beat health-check write failed: ..."
#        logged as an ERROR, and beat keeps ticking normally afterwards --
#        no crash, no restart.
#   5. Recreate the table before continuing:
#        docker compose exec postgres psql -U postgres -d erp_celery_poc \
#          -c 'CREATE TABLE erp_celery_poc."beatTime" (id uuid primary key, "updatedAt" timestamp not null);'
#
# Part 2 -- BUG #2/#3 (no HTTP timeout / no Celery task_time_limit):
#   (2026-07-21) The outbound-HTTP demo task (slow_http_task) and its
#   httpbin/hangserver test doubles were removed to keep this POC to just
#   web/beat/worker + Postgres, matching the shape this will take when
#   reused across other services. The underlying fixes are both still in
#   place and unaffected by that removal:
#     - src/handler/requestHandler.py defaults its `timeout` to
#       settings.DEFAULT_HTTP_TIMEOUT_SECONDS instead of None (fix #2).
#     - src/config/__init__.py sets task_time_limit/task_soft_time_limit
#       on the Celery app (fix #3).
#   There is no longer a demo task exercising either one directly; wire a
#   real outbound-HTTP periodic task back in (via requestHandler.handle_request)
#   if you need to re-verify this behavior end-to-end.
#
# Part 3 -- BUG #4/#5 (process supervision / port mismatch):
#   1. docker compose up -d beat
#   2. Reproduce a genuine crash (see Part 1 step 3 -- temporarily revert
#      the try/except fix, rebuild `beat`, drop `beatTime`).
#   3. FIXED (current run.sh + docker-compose.yml, three separate
#      services): `docker inspect erp-celery-poc-beat-1 --format
#      '{{.RestartCount}}'` increments from 0 to 1 -- Docker's own
#      `restart: unless-stopped` policy noticed the container's PID 1
#      (Beat, run via `exec` in run.sh) exit non-zero and restarted just
#      that one container. `web`/`worker` stay at RestartCount=0
#      throughout -- Beat dying can no longer take (or hide) anything else
#      down with it, since it's not sharing a container anymore.
#      Port 5007 is consistent between the Dockerfile EXPOSE,
#      docker-compose.yml's "5007:5007" mapping (on `web` only), and PORT
#      in .env.example (erp-managment's docker-compose.yml mismatched
#      10000:10000 vs the app's actual 5007).
#   NOTE: `docker kill <container>` (external SIGKILL) does NOT trigger
#      `restart: unless-stopped` in this particular sandbox's Docker
#      daemon (verified against a disposable throwaway container too --
#      not specific to this project). A genuine unhandled-exception crash
#      (a normal non-zero process exit) restarts correctly, which is also
#      the realistic scenario for bug #1 anyway.
echo "See the comments at the top of this file for the manual walkthrough; also see README.md."
