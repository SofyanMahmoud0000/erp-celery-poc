from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from src.config.config import settings
from src.handler.errorHandler import BadRequest
from src.models import db
from src.models.beatTime import BeatTime


class BeatTimeController:
    @staticmethod
    def update_beat_time():
        """
        Called directly inside CustomScheduler.apply_entry() below, once
        per beat tick, as a liveness self-check -- same pattern as
        erp-managment. Not a Celery task: it's never dispatched via
        .delay()/.apply_async(), so it doesn't need to be one -- the
        caller wraps this in app.app_context() instead.
        """
        beat_time: Optional[BeatTime] = db.session.query(BeatTime).first()
        if beat_time is None:
            beat_time = BeatTime()
        beat_time.updatedAt = datetime.now()
        db.session.add(beat_time)
        db.session.commit()

    @staticmethod
    def get_beat_time() -> Optional[BeatTime]:
        return db.session.query(BeatTime).first()

    @staticmethod
    def is_beat_healthy() -> Dict[str, Any]:
        beat_time = BeatTimeController.get_beat_time()
        if beat_time is None:
            raise BadRequest("Unhealthy beat: no beatTime row yet")

        next_expected_time = beat_time.updatedAt + timedelta(seconds=settings.DB_WRITE_TASK_INTERVAL_SECONDS * 3)
        if next_expected_time >= datetime.now():
            return {"health": "ok", "lastBeat": beat_time.updatedAt.isoformat()}
        raise BadRequest("Unhealthy beat: stale beatTime row")
