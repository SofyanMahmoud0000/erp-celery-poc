import uuid
from datetime import datetime, UTC

from sqlalchemy import UUID, DateTime
from sqlalchemy.orm import mapped_column, Mapped

from src.config.config import settings
from src.models import db


class BeatTime(db.Model):
    __tablename__ = 'beatTime'
    __table_args__ = {'schema': settings.SCHEMA_NAME}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now(UTC), onupdate=datetime.now(UTC))
