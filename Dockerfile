FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR /var/app

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --no-interaction

COPY . .
RUN chmod +x run.sh

# FIX #5 (was: docker-compose.yml mapped host 10000:10000 but the app
# binds 5007 inside the container -- silent port mismatch). Standardize
# on 5007 everywhere (see docker-compose.yml + .env.example PORT=5007).
EXPOSE 5007

# No image-level HEALTHCHECK here: `web`, `beat`, and `worker` are three
# separate services (see docker-compose.yml) each running a different
# single process from this same image (SERVICE_TYPE=web|beat|worker, see
# run.sh), and each needs a DIFFERENT liveness check (HTTP /health for
# web, a direct beatTime freshness check for beat, `celery inspect ping`
# for worker) -- those are defined per-service in docker-compose.yml
# rather than one-size-fits-all here.

CMD ["/bin/bash", "run.sh"]
