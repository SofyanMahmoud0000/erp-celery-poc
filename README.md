# erp-celery-poc

Standalone Flask + Celery + Beat proof-of-concept extracted from
`erp-managment`, built to reproduce -- and then fix, in isolation -- three
confirmed Celery/Beat reliability bugs from that service:

1. `CustomScheduler.apply_entry` had no `try/except` around its Beat
   health-check write -- an exception there killed the entire Beat
   process, unsupervised.
2. `requestHandler.handle_request` defaulted `timeout=None` -- outbound
   HTTP calls could hang forever.
3. `make_celery` set no `task_time_limit`/`task_soft_time_limit` --
   nothing bounded how long a task (e.g. one blocked on #2) could occupy
   a worker slot.

Also fixed as part of the same effort (not requiring before/after demos):

4. `run.sh` started Beat as a background `&` job and then `exec`'d
   gunicorn over PID 1 -- Beat became an orphaned, unsupervised process
   whose death was invisible.
5. `docker-compose.yml` mapped host `10000:10000` while the app bound
   `5007` inside the container.
6. `CustomError.__init__` called `super().__init__()` with no args, so
   `str(e)` was always `''` for any `CustomError` subclass.

**Architecture correction (2026-07-19):** Beat and Gunicorn originally ran
bundled together in one `web` container (matching erp-managment's current
`SERVICE_TYPE=gunicorn` combined shape), supervised in-container via a
`wait -n` + trap in `run.sh`. Per explicit request, this was split into
**three separate services** instead -- `web` (Gunicorn only), `beat`
(Celery Beat only), `worker` (Celery worker) -- because Beat must be a
strict singleton (never scaled) while `web` is exactly what you *do* want
to scale horizontally; bundling them forces workarounds that a clean split
avoids by construction. See "Process topology" below for the full
reasoning and re-verification.

This is a POC, not a production extraction: task bodies here are just two
representative examples (a DB-write task and an HTTP-call task), not the
full ~15 periodic tasks in erp-managment. The private `backend-common`
git dependency is replaced with a local stub (`src/handler/logger.py`)
since that repo isn't reachable from this sandbox.

**Broker correction (2026-07-19):** this POC originally (incorrectly) used
Redis as the Celery broker. erp-managment's actual `.env` configures the
broker as **Postgres itself**, via kombu's built-in `sqla+` SQLAlchemy
transport (`CELERY_BROKER_URL=sqla+postgresql://...` under its `[CELERY]`
section) -- not Redis. This POC now matches that: `settings.CELERY_BROKER_URL`
defaults to `sqla+` + the same Postgres DB used for everything else (models,
result backend, Beat schedule).

**Redis/caching + hangserver + httpbin removed (2026-07-21):** Flask-Caching
and its Redis backend (`init_cache`, `REDIS_*` settings, the `redis`
compose service), `hangserver` (the "never responds" TCP test double), and
`httpbin` + the `slow_http_task` demo task that called it were all dropped
-- none of them are needed to match the shape this will take when reused
across other services (just Postgres + web/beat/worker). The two fixes
that task existed to demonstrate (fix #2: `requestHandler`'s HTTP timeout
default; fix #3: Celery's `task_time_limit`/`task_soft_time_limit`) are
still in the code (`src/handler/requestHandler.py`,
`src/config/__init__.py`) -- there's just no demo task exercising them
live anymore. See `scripts/demo_bugs.sh` Part 2 for how to re-verify them
if needed.

Note: erp-managment's *current* `src/config/__init__.py` code still
hardcodes a `redis://` broker built from `CELERY_REDIS_*` settings that
aren't set anywhere in its own `.env` -- this looks like dead/stale config
there (its `.env`'s intended `sqla+postgresql://` broker is never actually
read by that code path, since `Settings` doesn't even declare a
`CELERY_BROKER_URL` attribute). Also, if that `sqla+` broker URL *were*
wired up as-is in erp-managment, its `broker_transport_options` (Redis-only
keys: `socket_keepalive`/`health_check_interval`/`visibility_timeout`)
would break it -- kombu's SQLAlchemy transport passes `transport_options`
straight into `sqlalchemy.create_engine(**opts)`, which raises
`TypeError: Invalid argument(s) ...` for those keys (verified locally).
This is flagged here for awareness only -- erp-managment itself was not
modified (outside this POC's write boundary).

## Layout

- `app.py` -- entry point (`app`, `celery` = `app.celery`)
- `src/config/__init__.py` -- `make_celery`/`ContextTask`/app factory (fixes #3 here)
- `src/config/config.py` -- `Settings`
- `src/config/scheduleTasks.py` -- `CustomScheduler` (fix #1 here) + periodic task registration
- `src/controller/beatTimeController.py` -- Beat health-check write/read (`update_beat_time`, `is_beat_healthy`)
- `src/controller/demoController.py` -- the representative periodic task: `db_write_task`
- `src/handler/requestHandler.py` -- outbound HTTP wrapper (fix #2 here)
- `src/handler/errorHandler.py` -- `CustomError` hierarchy (fix #6 here)
- `src/handler/logger.py` -- local stand-in for `backend_common.Logger`
- `src/models/` -- `BeatTime`, `Task` (SQLAlchemy), `sqlalchemy_celery_beat` DB wiring
- `src/apis/health.py` -- `/health`, `/health/beatStatus`
- `scripts/beat_healthcheck.py` -- standalone Beat liveness check (direct Postgres query, no Flask/HTTP needed) used by the `beat` service's healthcheck
- `scripts/worker_healthcheck.py` -- standalone worker liveness check (process-existence, not `celery inspect ping` -- see "Process topology")
- `scripts/demo_bugs.sh` -- documents the exact manual repro/fix-verification steps
- `run.sh` / `Dockerfile` / `docker-compose.yml` -- fixes #4/#5 (process supervision, restart policy, healthchecks, matching ports); see "Process topology" below

## Process topology: why Beat, Gunicorn, and the worker are three separate services

`docker-compose.yml` defines three services built from the same image
(`SERVICE_TYPE=web|beat|worker` picks which single process `run.sh`
`exec`s as PID 1 -- see `run.sh`):

- **`web`** -- Gunicorn only, serves the Flask API (`/health`, `/health/beatStatus`).
- **`beat`** -- Celery Beat only. Deliberately a singleton: no `ports:`, no scaling.
- **`worker`** -- the Celery worker. The thing you'd actually scale out for throughput.

This is deliberately **not** erp-managment's current shape (Beat +
Gunicorn bundled into one container/process group via `SERVICE_TYPE=gunicorn`
+ an in-container `wait -n`/trap to supervise the pair). Reasoning:

- **Beat must be a strict singleton; `web` must not be.** More than one
  Beat instance means every periodic task fires multiple times (duplicate
  payments, duplicate acknowledgements, etc.) -- genuinely dangerous for
  this kind of service. `web` is exactly what you *do* want to scale
  horizontally. Bundling them means you can never scale `web` replicas
  without also multiplying Beat, forcing workarounds (leader election,
  flags) instead of the singleton property being true by construction.
- **Independent failure/restart domains.** A Gunicorn worker recycling
  (deploys, `max_requests`, OOM) has nothing to do with Beat's health and
  shouldn't be able to affect it, or vice versa.
- **Each container now runs exactly one process**, so `run.sh` no longer
  needs the `wait -n` + trap dance the combined version required --
  Docker's own `restart:` policy handles a dead process per-service.
- **Per-role healthchecks.** `beat` has no HTTP server, so it can't reuse
  `web`'s `/health` endpoint -- `scripts/beat_healthcheck.py` checks
  `beatTime` freshness directly against Postgres instead. `worker`'s
  healthcheck could *not* use the "obvious" `celery inspect ping` -- see
  below.

### Finding: `celery inspect ping`/`celery status` don't work over the `sqla+` broker

While wiring up the `worker` service's healthcheck, `celery -A app.celery
inspect ping` reliably failed with `Error: No nodes replied within time
constraint` **even against a fully healthy, actively-processing worker**.
Root cause: Celery's remote-control/inspect commands go over the broker's
fanout/broadcast exchange (the "pidbox"), and kombu's `sqla+` SQLAlchemy
transport explicitly does not support fanout (see its own module
docstring: `Supports Fanout: no`). This is a real, structural limitation
of using Postgres as the broker, not a config mistake -- `scripts/worker_healthcheck.py`
checks worker process liveness directly instead (broker-agnostic, but
doesn't prove no individual task is stuck -- that's what fix #3's
`task_time_limit`/`task_soft_time_limit` are for).

### Re-verified after the split

- Brought up all three services (`web`, `beat`, `worker`) fresh --  all
  three reported `healthy`.
- Re-ran the bug #1 before/after test against the new topology: reverted
  the `try/except` fix in `scheduleTasks.py`, rebuilt just the `beat`
  service, dropped `beatTime` -- `beat`'s container genuinely crashed
  (`CRITICAL: beat raised exception ... ProgrammingError`, `docker inspect
  erp-celery-poc-beat-1 --format '{{.RestartCount}}'` went from `0` to
  `1`) and Docker restarted **only** the `beat` container -- `web` and
  `worker` were completely unaffected (`RestartCount=0` throughout).
  Re-applied the fix, rebuilt, confirmed `beat` healthy again with no
  further crashes.
- **Environment note:** in this sandbox, `docker kill <container>`
  (external SIGKILL) does **not** trigger the `restart: unless-stopped`
  policy at all -- verified this is a sandbox/daemon quirk, not specific
  to this project, by reproducing it against a disposable throwaway
  `alpine` container too. A genuine unhandled-exception crash (a normal
  non-zero process exit, which is exactly how bug #1 actually manifests)
  restarts correctly, as shown above -- that's the realistic scenario this
  POC needed to prove anyway.

## Running it locally

### Option A: full docker-compose stack (recommended)

```bash
cd /mnt/storage/settle/erp-celery-poc
cp .env.example .env   # only needed if you also want to run things outside docker-compose
docker compose up -d --build
docker compose ps                            # postgres/web/beat/worker should all be "healthy"
curl http://127.0.0.1:5007/health
curl http://127.0.0.1:5007/health/beatStatus
docker compose logs -f web beat worker       # watch gunicorn + beat ticks + task execution
```

`web` runs Gunicorn (the Flask API), `beat` runs Celery Beat (singleton
scheduler), `worker` runs the Celery worker -- three separate services,
see "Process topology" above for why.

Tear down: `docker compose down -v`

### Option B: host Python + ad hoc containers (faster iteration)

```bash
cd /mnt/storage/settle/erp-celery-poc
python3 -m venv .venv && source .venv/bin/activate
pip install flask==3.0.3 flask-sqlalchemy==3.1.1 flask-migrate==4.0.7 \
  "celery[sqlalchemy]==5.4.0" kombu==5.4.0 \
  sqlalchemy==2.0.29 psycopg2-binary==2.9.9 sqlalchemy-celery-beat==0.8.0 \
  python-dotenv==1.0.1 requests==2.32.3 flower==2.0.1 gunicorn==23.0.0

docker run -d --name poc-postgres -p 15432:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=erp_celery_poc \
  postgres:16

cat > .env <<'EOF'
SECRET_KEY=dev-secret
PORT=5007
POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:15432/erp_celery_poc
CELERY_BROKER_URL=sqla+postgresql://postgres:postgres@127.0.0.1:15432/erp_celery_poc
CELERY_RESULT_BACKEND=db+postgresql://postgres:postgres@127.0.0.1:15432/erp_celery_poc
DB_WRITE_TASK_INTERVAL_SECONDS=10
CELERY_TASK_TIME_LIMIT=60
CELERY_TASK_SOFT_TIME_LIMIT=45
DEFAULT_HTTP_TIMEOUT_SECONDS=5
EOF

python3 -c "from app import app"       # creates schema + tables
celery -A app.celery worker --loglevel=info --concurrency=2 &
celery -A app.celery beat --loglevel=info &
```

## Bug reproduction / fix verification (what was actually run)

All three commands below were executed against this codebase during
development. See `scripts/demo_bugs.sh` for the same steps written out for
docker-compose. Summary of results:

### Bug #1 -- Beat crashes on an unhandled exception in `apply_entry`

**Before fix** (`apply_entry` calling `BeatTimeController.update_beat_time()`
with no try/except): dropped the `beatTime` table while Beat was running,
then waited for the next tick.

```
[... CRITICAL/MainProcess] beat raised exception <class 'sqlalchemy.exc.ProgrammingError'>: ...
relation "erp_celery_poc.beatTime" does not exist ...
```
followed by the Beat process exiting entirely (`pgrep -fa "celery -A app.celery beat"` returned nothing afterwards -- confirmed the process was gone, not just idling).

**After fix** (try/except + `logger.error(...)` added around the call in
`src/config/scheduleTasks.py`): same DB break, but now:
```
[... ERROR/MainProcess] CustomScheduler.apply_entry: beat health-check write failed: (psycopg2.errors.UndefinedTable) ...
```
and Beat keeps running, continuing to send other due periodic tasks on schedule -- the process never dies.

### Bug #2/#3 -- hung outbound call blocks a worker slot forever

**Before fix** (`timeout=None` in `requestHandler.handle_request`, no
`task_time_limit`/`task_soft_time_limit` in `make_celery`): sent
`slow_http_task` pointed at `scripts/hang_server.py` (accepts a TCP
connection, never responds).

```
$ celery -A app.celery inspect active     # ~60s after the task was sent
    * {'id': '...', 'name': '...slow_http_task', ..., 'time_start': 1784447670.89, ...}
```
Task was still "active" 60+ seconds later with **zero further log output**
after the initial "slow_http_task calling ..." line -- confirming it was
genuinely stuck, not just slow.

**After fix** (`DEFAULT_HTTP_TIMEOUT_SECONDS=5` default in
`requestHandler.py`, `task_time_limit=60`/`task_soft_time_limit=45` in
`make_celery`):

```
[... INFO] slow_http_task calling http://127.0.0.1:19191/ (http_timeout=None)
[... ERROR/ForkPoolWorker-1] Task ...slow_http_task[...] raised unexpected:
    ReadTimeout(ReadTimeoutError("...: Read timed out. (read timeout=5.0)"))
```
Failed in ~5s (`10:58:32` -> `10:58:37`); `celery inspect active` immediately
showed the worker slot free again (`- empty -`).

To prove the **Celery-level** guardrail works independently of the HTTP-level
fix (matching the documented "raw `requests.put/post` bypasses the handler
with no timeout at all" bug), the same task was sent with an explicit
`http_timeout=300` (defeating the 5s default):
```
[11:00:06] slow_http_task calling http://127.0.0.1:19191/ (http_timeout=300)
[11:00:51] WARNING: Soft time limit (45s) exceeded for ...slow_http_task[...]
[11:00:51] ERROR: Task ...slow_http_task[...] raised unexpected: SoftTimeLimitExceeded()
```
Exactly 45s later (`CELERY_TASK_SOFT_TIME_LIMIT`), Celery itself killed the
task and reclaimed the worker slot, even with an HTTP timeout that would
never have fired.

**Broker note:** the three transcripts above were captured while this POC
still (incorrectly) used a Redis broker -- see the "Broker correction"
paragraph earlier in this README. All three bugs/fixes are independent of
broker choice (they're about the Beat health-check call, the HTTP client
timeout, and Celery's own task time limits, none of which touch the
broker), but for completeness this was re-verified end-to-end against the
corrected `sqla+postgresql://` (DB) broker in the full `docker compose`
stack:
```
worker-1 | .> transport: sqla+postgresql://postgres:**@postgres:5432/erp_celery_poc
worker-1 | [...] Connected to sqla+postgresql://postgres:**@postgres:5432/erp_celery_poc
```
- Bug #1 re-verified: dropped `beatTime` again with `web` running on the DB
  broker -- `CustomScheduler.apply_entry: beat health-check write failed: ...`
  was logged, `docker compose ps web` stayed `healthy`, no crash.
- Bug #2/#3 re-verified: sent `slow_http_task` at `hangserver:19191` via
  `docker compose exec worker python3 -c "..."` -- failed with
  `requests.exceptions.ReadTimeout: HTTPConnectionPool(host='hangserver', port=19191): Read timed out. (read timeout=5.0)`
  in exactly 5s (`13:02:46` -> `13:02:51`).
- A `db_write_task` produced by Beat and consumed by the worker over the DB
  broker also round-tripped successfully end-to-end (`select * from
  erp_celery_poc."Tasks"` showed the new row), confirming the broker switch
  didn't break normal task flow.

### Bug #4/#5 -- process supervision + port mismatch (docker-compose)

Originally verified against the (now superseded) combined `web` container
running Beat+Gunicorn together: killing Beat inside that container caused
`run.sh`'s `wait -n` to notice, kill the sibling Gunicorn process, and
exit non-zero -- causing the whole container to stop and Docker's
`restart: unless-stopped` policy to bring it back up fresh
(`RestartCount` went `0` -> `1`).

After splitting into three separate services (`web`/`beat`/`worker` --
see "Process topology" above), re-verified the equivalent scenario
directly: reverted the bug #1 fix, dropped `beatTime`, and confirmed
**only** the `beat` container crashed and restarted
(`docker inspect erp-celery-poc-beat-1 --format '{{.RestartCount}}'` ->
`1`) while `web` and `worker` stayed at `RestartCount=0` the whole time --
i.e. Beat dying no longer has any way to also take down (or hide behind)
the web process, since they're not in the same container anymore. Fix
re-applied and reconfirmed stable afterwards.

Port `5007` is consistent across `Dockerfile` (no image-level
`HEALTHCHECK` anymore -- each service defines its own, see "Process
topology"), `docker-compose.yml` (`"5007:5007"` on `web` only; `beat`/
`worker` don't need a published port), and `.env.example` (`PORT=5007`) --
erp-managment's `docker-compose.yml` mismatched `10000:10000` against the
app's actual `5007`.

## Known simplifications vs. the real erp-managment service

- Only 2 of the ~15 real periodic tasks are represented here.
- No Alembic migrations are wired up (schema is created via
  `db.create_all()` in `src/models/__init__.py` for simplicity); adding
  real migrations would follow the same `flask-migrate` pattern as
  erp-managment.
- `backend-common` (private git dependency) is stubbed locally
  (`src/handler/logger.py`) rather than installed -- swap this back in if
  /when this code is used somewhere with access to that repo (see the
  comment in `pyproject.toml`).
- No queue routing/isolation is added here either (same as erp-managment)
  -- out of scope for this reliability-focused POC.
