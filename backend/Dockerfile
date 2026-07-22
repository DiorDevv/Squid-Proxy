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
COPY docker-entrypoint.sh ./

RUN pip install --no-cache-dir . \
    && chmod +x docker-entrypoint.sh

RUN useradd --create-home --shell /bin/false appuser \
    # Pre-create the demo/shared log volume mount point, and the archive
    # output directory (see app/services/archive_scheduler.py), owned by
    # appuser. Docker initializes a fresh named volume from the image's
    # directory contents (including ownership) on first mount, so this makes
    # both volumes writable by the non-root user without needing a root
    # entrypoint.
    && mkdir -p /data/squid-logs /app/archives \
    && chown -R appuser:appuser /data/squid-logs /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# --proxy-headers/--forwarded-allow-ips: trusts X-Forwarded-For from any
# peer, which is only safe because this container is no longer reachable
# except through the frontend's nginx (see docker-compose.yml's backend
# port binding) -- without this, every request's peer is nginx itself, and
# per-IP rate limiting (app/core/rate_limit.py) collapses into one bucket
# shared by every real client.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
