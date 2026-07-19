FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tooling only needed transiently for compiled deps (e.g. bcrypt).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY alembic.ini ./

RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /bin/false appuser \
    # Pre-create the demo/shared log volume mount point owned by appuser.
    # Docker initializes a fresh named volume from the image's directory
    # contents (including ownership) on first mount, so this makes the
    # volume writable by the non-root user in both the backend and
    # demo-log-generator services without needing a root entrypoint.
    && mkdir -p /data/squid-logs \
    && chown -R appuser:appuser /data/squid-logs /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
