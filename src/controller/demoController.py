import uuid

from src.config import celery, settings
from src.models import db
from src.models.tasks import Task
import time

logger = settings.logger


class DemoController:
    """
    Representative periodic task standing in for the ~15 real periodic
    tasks in erp-managment's scheduleTasks.py:

    - db_write_task: a plain DB-touching task (like the Task/Log
      "acknowledge" tasks), used to prove the app-context + SQLAlchemy
      wiring works end-to-end.

    - finish_name_task: an on-demand task (not scheduled by Beat), fired
      from an API call instead -- see POST /tasks/finishName in
      src/apis/tasks.py.
    """

    @staticmethod
    @celery.task(bind=True)
    def db_write_task(self):
        time.sleep(35)
        task = Task()
        task.id = uuid.uuid4()
        task.type = "demo"
        task.taskStatus = "SUCCEEDED"
        db.session.add(task)
        db.session.commit()
        return str(task.id)

    @staticmethod
    @celery.task
    def finish_name_task(name: str) -> str:
        return name + "finished"
