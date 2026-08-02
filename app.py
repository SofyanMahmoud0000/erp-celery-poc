from flask import Flask

from src.config import init_app

app: Flask = init_app()
celery = app.celery  # used by `celery -A app.celery worker/beat ...`

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(app.config.get("PORT", 5007)), debug=True)
