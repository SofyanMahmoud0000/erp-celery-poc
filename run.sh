#!/bin/bash
#
# Each container built from this image now runs exactly ONE process
# (web = Gunicorn only, beat = Celery Beat only, worker = Celery worker
# only -- see docker-compose.yml), so this script just `exec`s the right
# single command as PID 1 based on SERVICE_TYPE. There's no
# multi-process supervision logic left here on purpose: Docker itself
# (via each service's `restart: unless-stopped` + healthcheck) is what
# notices a dead process and restarts that one container -- a crash of
# Beat no longer has any way to silently coexist with a still-running
# Gunicorn (or vice versa), because they're not in the same container
# anymore. This replaces the earlier single-container
# "beat + gunicorn as supervised siblings" approach.
set -euo pipefail

# Step 1: run DB migrations (idempotent; also handled by db.create_all()
# in src/models/__init__.py for this POC, but `flask db upgrade` is kept
# here to mirror the real service and to be a no-op once Alembic
# migrations are added). Note: with three services all starting at once,
# this (and the equivalent db.create_all() triggered by importing app.py)
# may run concurrently on first boot -- fine for this POC's idempotent
# `CREATE TABLE IF NOT EXISTS`-style setup; a real deployment would move
# this to a single init/migration job instead of running it per-service.
flask db upgrade || echo "flask db upgrade: nothing to do / no migrations yet"

# Step 2: load .env if present
if [[ -f .env ]]; then
  set -a
  source <(grep -vE '^\[.*\]$' .env | sed -E 's/^(.*)=(.*)$/\1="\2"/')
  set +a
else
  echo "Warning: .env file not found!"
fi

case "${SERVICE_TYPE:-worker}" in
  web)
    echo "Starting Gunicorn..."
    exec gunicorn --bind "0.0.0.0:${PORT:-5007}" --log-level debug app:app --timeout 120 -w 5
    ;;
  beat)
    echo "Starting Celery Beat..."
    exec celery -A app.celery beat --loglevel=info
    ;;
  worker)
    echo "Starting Celery Worker..."
    exec celery -A app.celery worker --loglevel=info --concurrency=4
    ;;
  *)
    echo "Unknown SERVICE_TYPE='${SERVICE_TYPE:-}' (expected web|beat|worker)" >&2
    exit 1
    ;;
esac
