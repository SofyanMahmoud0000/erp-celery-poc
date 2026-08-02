import uuid
from datetime import datetime, UTC

from sqlalchemy import UUID, String, DateTime
from sqlalchemy.orm import mapped_column, Mapped

from src.config.config import settings
from src.models import db


class Task(db.Model):
    """
    Minimal stand-in for erp-managment's src/models/tasks.py -- trimmed to
    just enough columns to exercise a representative "DB write" periodic
    task (see src/controller/demoController.py::db_write_task).
    """
    __tablename__ = 'Tasks'
    __table_args__ = {'schema': settings.SCHEMA_NAME}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    taskStatus: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING")
    createdAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now(UTC))
    updatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now(UTC), onupdate=datetime.now(UTC))
