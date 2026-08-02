import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

from src.handler.logger import Logger


class Settings:
    PROJECT_NAME: str = "ERP Celery POC"
    PROJECT_VERSION: str = "0.0"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    PORT = os.getenv("PORT", "5007")

    POSTGRES_URL: str = os.getenv("POSTGRES_URL")
    SCHEMA_NAME = os.getenv("SCHEMA_NAME", "erp_celery_poc")

    DEBUG = os.getenv("DEBUG", default="False") == "True"

    # NOTE (corrected 2026-07-19): erp-managment's real .env configures
    # Celery's BROKER as Postgres itself, via kombu's built-in `sqla+`
    # SQLAlchemy transport (`CELERY_BROKER_URL=sqla+postgresql://...`
    # under its `[CELERY]` section) -- NOT Redis. This POC originally
    # (incorrectly) built a `redis://` broker URL from CELERY_REDIS_*
    # settings; that's now replaced with this single CELERY_BROKER_URL,
    # defaulting to `sqla+` + the same Postgres DB used everywhere else,
    # matching production. See src/config/__init__.py::make_celery.
    #
    # (erp-managment's actual `src/config/__init__.py` code still
    # hardcodes a `redis://` broker built from `CELERY_REDIS_*` settings
    # that aren't even present in its `.env` -- appears to be dead/stale
    # config there, not something reproduced here. See MEMORY for detail.)
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")

    # Default the broker to the same Postgres DB, via kombu's `sqla+`
    # transport, if CELERY_BROKER_URL isn't set explicitly.
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or (
        f"sqla+{POSTGRES_URL}" if POSTGRES_URL else None
    )

    # How often the demo periodic task runs (seconds). Kept short for
    # local/demo purposes -- real service uses minutes.
    DB_WRITE_TASK_INTERVAL_SECONDS = int(os.getenv("DB_WRITE_TASK_INTERVAL_SECONDS", 5))

    CELERY_NETWORK_FAILURE_MAX_RETRIES = int(os.getenv("CELERY_NETWORK_FAILURE_MAX_RETRIES", 3))
    CELERY_NETWORK_FAILURE_RETRY_BACKOFF = int(os.getenv("CELERY_NETWORK_FAILURE_RETRY_BACKOFF", 5))
    CELERY_NETWORK_FAILURE_RETRY_JITTER = bool(os.getenv("CELERY_NETWORK_FAILURE_RETRY_JITTER", True))

    # --- Fix #3: Celery-level guardrails against a hung task (see src/config/__init__.py) ---
    CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", 40))
    CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", 30))

    # --- Fix #2: default outbound HTTP timeout (seconds) used by requestHandler ---
    DEFAULT_HTTP_TIMEOUT_SECONDS = float(os.getenv("DEFAULT_HTTP_TIMEOUT_SECONDS", 5))

    # kombu's `sqla+` broker transport never deletes a message row after
    # it's consumed (see kombu.transport.sqlalchemy.Channel._get -- it
    # just flips `visible` to False), so kombu_message grows unbounded
    # unless something purges it. Unlike celery_taskmeta (swept daily by
    # Celery's own built-in celery.backend_cleanup task), there's no
    # built-in equivalent for the broker's own tables -- see
    # CustomScheduler / purge_consumed_broker_messages in scheduleTasks.py.
    KOMBU_MESSAGE_CLEANUP_INTERVAL_SECONDS = int(os.getenv("KOMBU_MESSAGE_CLEANUP_INTERVAL_SECONDS", 3600))
    KOMBU_MESSAGE_RETENTION_SECONDS = int(os.getenv("KOMBU_MESSAGE_RETENTION_SECONDS", 86400))

    logger = Logger("config")


settings = Settings()
