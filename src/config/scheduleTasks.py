from celery import Celery
from sqlalchemy_celery_beat.schedulers import DatabaseScheduler

from src.config import celery, settings
from src.controller.beatTimeController import BeatTimeController
from src.models import db

logger = settings.logger


class CustomScheduler(DatabaseScheduler):
    def apply_entry(self, entry, producer=None):
        # Deferred import (like DemoController below): by the time a tick
        # actually happens, app.py's module-level `app = init_app()` has
        # long finished, so this is safe -- importing it at module level
        # here would be circular (init_app() -> register_schedule_tasks()
        # -> this module, before app.py finishes assigning `app`).
        from app import app

        # FIX #1 (was: no try/except -- an uncaught exception here killed
        # the whole Beat process, unsupervised). The health-check write is
        # a best-effort liveness signal; it must never be allowed to take
        # Beat down with it. Log-and-continue so `GET /health/beatStatus`
        # correctly reports staleness instead of the whole process dying
        # silently. See scripts/demo_bugs.sh part 1 for the before/after.
        try:
            with app.app_context():
                BeatTimeController.update_beat_time()
        except Exception as e:
            logger.error(f"CustomScheduler.apply_entry: beat health-check write failed: {e}")
        return super().apply_entry(entry, producer)


@celery.task
def purge_consumed_broker_messages():
    """
    kombu's `sqla+` broker transport never deletes a message row once
    consumed (Channel._get() only flips `visible` to False), so
    kombu_message grows forever unless something purges it -- unlike
    celery_taskmeta, which Celery's own built-in celery.backend_cleanup
    task already sweeps daily. This is that same idea, applied to the
    broker's own table instead of the result backend's.
    """
    result = db.session.execute(
        db.text(
            f'DELETE FROM "{settings.SCHEMA_NAME}".kombu_message '
            'WHERE visible = false AND "timestamp" < now() - make_interval(secs => :retention)'
        ),
        {"retention": settings.KOMBU_MESSAGE_RETENTION_SECONDS},
    )
    deleted = result.rowcount
    db.session.commit()
    logger.info(f"purge_consumed_broker_messages: deleted {deleted} row(s)")


@celery.on_after_configure.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    sender.conf.beat_scheduler = "src.config.scheduleTasks.CustomScheduler"

    from src.controller.demoController import DemoController

    sender.add_periodic_task(
        settings.DB_WRITE_TASK_INTERVAL_SECONDS,
        DemoController.db_write_task.s(),
        name="Demo: representative DB-write periodic task",
    )
    sender.add_periodic_task(
        settings.KOMBU_MESSAGE_CLEANUP_INTERVAL_SECONDS,
        purge_consumed_broker_messages.s(),
        name="Purge consumed kombu_message rows (broker table maintenance)",
    )
