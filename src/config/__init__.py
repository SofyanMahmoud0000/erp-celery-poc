from typing import Optional

from celery import Celery
from celery.contrib.abortable import AbortableTask
from celery.signals import before_task_publish, worker_process_init
from flask import Flask

from .config import settings
from src.handler.errorHandler import register_errors, ExternalResourceFailed

celery: Optional[Celery] = None

logger = settings.logger


def make_celery(app: Flask) -> Celery:
    # keep the beat/result tables in our own schema, same as erp-managment
    from kombu.transport.sqlalchemy import metadata
    metadata.schema = settings.SCHEMA_NAME

    celery: Celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config['result_backend'],
    )

    class ContextTask(AbortableTask):
        autoretry_for = (ExternalResourceFailed,)
        max_retries = settings.CELERY_NETWORK_FAILURE_MAX_RETRIES
        retry_backoff = settings.CELERY_NETWORK_FAILURE_RETRY_BACKOFF
        retry_jitter = settings.CELERY_NETWORK_FAILURE_RETRY_JITTER

        def __call__(self, *args: tuple, **kwargs: dict) -> any:
            # Applies to every task registered on this Celery app (same
            # spirit as autoretry_for/max_retries above being set once here
            # for all tasks): every task needs a Flask app context to touch
            # Flask-SQLAlchemy's db.session. Celery's own worker logs
            # ("Task ... received" / "succeeded in Xs" / failure+traceback)
            # already cover start/success/failure -- no need to duplicate
            # them here.
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    celery.conf.update(
        task_track_started=True,
        result_extended=True,
        broker_connection_retry_on_startup=True,
        # FIX #3 (was: no task_time_limit/task_soft_time_limit at all, so a
        # hung outbound HTTP call -- see FIX #2 in requestHandler.py -- could
        # block a worker slot forever with zero log output). soft limit raises
        # SoftTimeLimitExceeded inside the task first (recoverable/loggable);
        # the hard limit SIGKILLs the worker child if it ignores that, so the
        # slot always gets reclaimed. See scripts/demo_bugs.sh part 2.
        task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
        task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    )
    celery.conf.update({"database_table_schemas": {'task': settings.SCHEMA_NAME, 'group': settings.SCHEMA_NAME}})
    celery.conf.update(app.config)

    # NOTE (corrected 2026-07-19): the broker is Postgres via kombu's `sqla+`
    # transport (see settings.CELERY_BROKER_URL / Settings.CELERY_BROKER_URL),
    # matching erp-managment's actual `.env` (`CELERY_BROKER_URL=sqla+postgresql://...`).
    # No `broker_transport_options` are set here -- Redis-only options like
    # `socket_keepalive`/`health_check_interval`/`visibility_timeout` are NOT
    # valid for this transport: kombu.transport.sqlalchemy.Channel passes
    # `transport_options` straight into `sqlalchemy.create_engine(**opts)`,
    # so passing those Redis-specific keys raises
    # `TypeError: Invalid argument(s) ... sent to create_engine()` the
    # instant the broker channel is opened. (erp-managment's current code
    # sets exactly those Redis-only options while also -- per its `.env` --
    # intending a `sqla+postgresql://` broker; that combination would be
    # broken in the way described above. See MEMORY for details -- flagged,
    # not fixed, since erp-managment itself is out of this POC's write
    # boundary.)

    return celery


@before_task_publish.connect
def log_before_task_publish(sender=None, headers=None, routing_key=None, **kwargs):
    # Fires right before the task message is inserted into the broker
    # (kombu_message, for this app's sqla+ transport) -- covers every
    # dispatch, whether it's Beat firing a periodic task or plain
    # .delay()/.apply_async() calls elsewhere. Celery itself logs nothing
    # at this step (Beat's own "Sending due task" line only covers
    # periodic tasks, not ad-hoc dispatches, and isn't a confirmation the
    # insert actually happened).
    #
    # Defined at module level (not nested inside make_celery()) on
    # purpose: Signal.connect() defaults to weak=True, so a receiver
    # with no other strong reference (e.g. a function nested inside
    # make_celery(), gone once that call returns) gets silently
    # garbage-collected and the connection just stops firing with no
    # error anywhere. A module-level function is kept alive for the
    # process's lifetime by the module's own namespace.
    task_id = (headers or {}).get('id')
    logger.info(f"[QUEUE INSERT] name={sender} id={task_id} routing_key={routing_key}")


@worker_process_init.connect
def dispose_engine_after_fork(**kwargs):
    # FIX #7 (psycopg2 connections are not fork-safe): app.py's module-level
    # `app = init_app()` opens a real SQLAlchemy/psycopg2 connection (via
    # db.create_all()) before Celery's prefork pool forks any worker child.
    # Each forked child inherits a *copy* of that connection pool, including
    # the live OS socket -- if two processes then use the same socket, the
    # libpq protocol state desyncs, surfacing as nonsense errors like
    # `psycopg2.DatabaseError: ... PGRES_TUPLES_OK and no message from the
    # libpq` or `sqlalchemy.exc.ResourceClosedError: ... does not return
    # rows` (seen on the post-commit attribute-refresh SELECT). This signal
    # fires in each child immediately after fork, before it picks up any
    # task, so disposing here forces every subsequent query in that child to
    # open a brand-new connection nobody else has ever touched.
    #
    # `close=False` is required, not optional: the plain `dispose()` default
    # actually CLOSES the inherited connections, i.e. sends real
    # close/terminate bytes down the socket -- but that socket's underlying
    # fd is still shared with the parent (and siblings forked at the same
    # time), so closing it from here can itself race with whatever they're
    # doing on it. Verified locally: with plain `dispose()`, the same
    # PGRES_TUPLES_OK/ResourceClosedError errors kept happening for several
    # minutes after every worker startup (all initial ForkPoolWorker-N
    # children racing their own dispose() against each other), only settling
    # once a task's hard time limit killed and replaced one of them. With
    # `close=False`, the pool's references are dropped without touching the
    # shared socket at all, so there's nothing left to race.
    from app import app
    from src.models import db

    with app.app_context():
        db.engine.dispose(close=False)


def register_schedule_tasks(celery: Celery):
    from src.config.scheduleTasks import setup_periodic_tasks
    setup_periodic_tasks(celery)


def init_apis(app: Flask):
    from src.apis.health import health_bp
    from src.apis.tasks import tasks_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(tasks_bp)


def init_app() -> Flask:
    app: Flask = Flask(__name__)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SECRET_KEY'] = settings.SECRET_KEY
    # Broker = Postgres via kombu's `sqla+` transport (matches erp-managment's
    # actual `.env`: `CELERY_BROKER_URL=sqla+postgresql://...`), NOT Redis.
    app.config['CELERY_BROKER_URL'] = settings.CELERY_BROKER_URL
    app.config['result_backend'] = settings.CELERY_RESULT_BACKEND
    app.config['SQLALCHEMY_DATABASE_URI'] = settings.POSTGRES_URL
    app.config['beat_scheduler'] = 'sqlalchemy_celery_beat.schedulers.DatabaseScheduler'

    from src.models import init_models
    init_models(app)

    global celery
    celery = make_celery(app)
    setattr(app, "celery", celery)
    register_schedule_tasks(celery)

    register_errors(app)
    init_apis(app)

    return app

