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
    # Pre-create the demo/shared log volume mount point, the archive output
    # directory (see app/services/archive_scheduler.py), the UT1 blacklist
    # cache directory (see app/services/ut1_blacklist.py), and the log
    # tailer's position-persistence directory (see
    # app/services/log_tailer.py), owned by appuser. Docker initializes a
    # fresh named volume from the image's directory contents (including
    # ownership) on first mount, so this makes all four volumes writable by
    # the non-root user without needing a root entrypoint.
    && mkdir -p /data/squid-logs /app/archives /app/ut1_blacklist_data /app/log_tailer_state \
    && chown -R appuser:appuser /data/squid-logs /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# --proxy-headers/--forwarded-allow-ips=127.0.0.1: safe default for running
# this image standalone (e.g. plain `docker run`, no reverse proxy in
# front) -- matches deploy/systemd's own default. docker-compose.yml's
# backend service OVERRIDES this default with the frontend container's
# actual (static-IP) address, since in that topology the trusted proxy is
# a sibling container, not localhost -- see that file's `command:` and
# `networks:` for the real trust boundary (network segmentation ensures
# only the frontend container can reach this one at all, and only its
# specific IP is trusted to set X-Forwarded-For). Never widen this to `*`:
# without a real restriction here, per-IP rate limiting
# (app/core/rate_limit.py) is trivially bypassed by anyone who can spoof
# the header.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
