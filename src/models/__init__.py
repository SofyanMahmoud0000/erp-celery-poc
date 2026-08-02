from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from src.config.config import settings

db = SQLAlchemy()


def init_models(app: Flask):
    db.init_app(app)

    from flask_migrate import Migrate
    Migrate(app, db)

    # Import models so they're registered on `db.metadata` for
    # `flask db upgrade` / `create_all()`.
    from src.models import beatTime, tasks  # noqa: F401

    # Point sqlalchemy-celery-beat's DatabaseScheduler at our own Postgres
    # DB/schema (same monkeypatch pattern as erp-managment's
    # src/models/__init__.py) -- otherwise it silently falls back to its
    # own sqlite:///schedule.db default.
    from sqlalchemy_celery_beat import schedulers
    schedulers.DEFAULT_BEAT_DBURI = settings.POSTGRES_URL
    schedulers.DEFAULT_BEAT_SCHEMA = settings.SCHEMA_NAME

    with app.app_context():
        db.session.execute(
            db.text(f'CREATE SCHEMA IF NOT EXISTS "{settings.SCHEMA_NAME}"')
        )
        db.session.commit()
        db.create_all()
