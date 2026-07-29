#!/usr/bin/env python3
"""
Standalone Celery worker liveness healthcheck.

`celery -A app.celery inspect ping` (the "obvious" worker healthcheck)
relies on Celery's remote-control/pidbox mechanism, which needs a
fanout-capable broker (Redis, RabbitMQ, ...). kombu's `sqla+` SQLAlchemy
transport used here does NOT support fanout (see its own module
docstring: "Supports Fanout: no"), so `inspect ping` never gets a reply
over this broker -- confirmed empirically: it fails with "No nodes
replied within time constraint" even while the worker is completely
healthy and actively processing tasks.

This checks Celery worker process liveness directly instead (broker
agnostic). Note this only proves the worker's MainProcess/ForkPoolWorker
processes exist -- it does NOT prove a given task isn't stuck (that's
what task_time_limit/task_soft_time_limit in src/config/__init__.py are
for; see FIX #3).
"""
import os
import sys


def main() -> int:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode(errors="ignore")
        except Exception:
            continue
        if "celery" in cmdline and "app.celery" in cmdline and "worker" in cmdline:
            print(f"worker healthcheck: ok -- pid {pid} alive")
            return 0
    print("worker healthcheck: no celery worker process found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
