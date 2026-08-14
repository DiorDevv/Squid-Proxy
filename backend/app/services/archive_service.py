"""Archives the last 7 days of raw event detail as gzip-compressed CSV before
retention.py permanently purges it (RETENTION_DAYS_RAW_EVENTS, default 7).

Delegates the actual row streaming to export_service.stream_csv (also used
by GET /api/export) rather than re-querying RawEvent itself, so the two
places that need "every row in a range, batched, no memory blowup" can't
quietly drift apart. This is the same reason that function -- not
export_as_csv's EXPORT_ROW_LIMIT-capped, in-memory-string sibling -- exists:
a week of raw events at the traffic volumes in the brief (1-3M req/day) is
millions of rows, and both this and the interactive download need the
complete range, not the most recent 100k.

Called from two places:
- app/services/archive_scheduler.py, an in-process background job that calls
  this automatically about once a week (see ARCHIVE_ENABLED/
  ARCHIVE_MIN_INTERVAL_SECONDS in app/core/config.py) -- the default,
  no-setup-required path.
- scripts/archive_weekly_export.py, a thin CLI wrapper around the same
  archive() function, for an immediate on-demand run or for anyone who'd
  rather keep this fully external (cron/systemd timer) instead
  (ARCHIVE_ENABLED=false).

One file per configured branch (report_scheduler.py sends reports the same
way), named squid-events-<branch>-<since_date>_<until_date>.csv.gz in
output_dir (or the same name plus a trailing .enc when ARCHIVE_ENCRYPTION_KEY
is set -- see below). Archive files older than keep_days are deleted after a
successful run -- rotation for the *archive* on this server, independent of
the live database's own retention window.

**Encryption at rest.** These files hold the same client-IP/domain-visited
detail the multi-branch TLS requirement protects in transit (see
ARCHITECTURE.md) -- with no key configured they'd otherwise sit on disk in
the clear indefinitely (up to ARCHIVE_KEEP_DAYS). When
settings.ARCHIVE_ENCRYPTION_KEY is set, the completed gzip file is encrypted
with it (Fernet: AES-128-CBC + HMAC, i.e. authenticated -- a tampered or
truncated file fails to decrypt rather than silently returning corrupt CSV)
before the atomic rename, and gets a trailing ".enc" on its filename so it's
never mistaken for a plain .csv.gz. Decrypt with
scripts/decrypt_archive.py. Encryption happens as one extra pass over the
already-gzipped bytes (not streamed inline with the CSV write) since Fernet
tokens aren't chunkable -- gzip has typically already shrunk a week of raw
events enough that holding the compressed form in memory once is cheap
relative to the row-streaming CSV generation itself.

Each successful per-branch write also upserts an ArchiveRun row
(branch -> archived up to `now`), which retention.py checks before its next
purge -- so if archiving ever stops running (disk full, disabled, etc.), the
next purge notices that branch was never (or not recently enough) archived
and warns instead of silently deleting it anyway.

The per-branch range normally covers a flat, deliberately-overlapping 7 days
back from `now` (each run re-covers most of what the previous one already
archived -- redundancy, not incrementality, is the point: this is what makes
a single missed run harmless with no gap-tracking logic needed for the
common case). It only extends back *further* than 7 days when
ArchiveRun.archived_until is already older than that -- i.e. more than one
run in a row was missed -- so that case doesn't silently skip the gap
between "7 days ago" and wherever the last successful run actually left off.
Because of the redundant-by-default 7-day window, calling archive() much
more often than the nominal weekly cadence is *not* free -- each call still
re-exports close to a full week of data -- which is exactly why
ArchiveScheduler checks far more often than it actually calls this (see its
own docstring).
"""

import gzip
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.models.archive_run import ArchiveRun
from app.models.db import AsyncSessionLocal
from app.services.export_service import stream_csv

logger = logging.getLogger(__name__)

# Matches both plain (squid-events-...csv.gz) and encrypted
# (squid-events-...csv.gz.enc) archives -- see "Encryption at rest" above.
ARCHIVE_FILENAME_GLOB = "squid-events-*.csv.gz*"


def _purge_old_archives(output_dir: Path, keep_days: int) -> None:
    cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
    for path in output_dir.glob(ARCHIVE_FILENAME_GLOB):
        # The broadened glob above also matches a still-being-written
        # ....csv.gz.tmp from a run currently in progress -- never a
        # concern in practice (this only runs after that same run's loop
        # has already renamed its own tmp file away) but excluded anyway
        # since matching it is accidental, not intended.
        if path.name.endswith(".tmp"):
            continue
        if path.stat().st_mtime < cutoff:
            path.unlink()
            logger.info("Purged old archive", extra={"path": str(path)})


async def archive(output_dir: Path, keep_days: int) -> None:
    # No init_db() here -- callers are expected to have already initialized
    # the schema: the in-process scheduler runs after the app's own
    # lifespan-startup init_db(), and the standalone CLI wrapper
    # (scripts/archive_weekly_export.py) calls it itself before this.
    settings = get_settings()
    now = datetime.now(UTC)
    default_since = now - timedelta(days=7)
    output_dir.mkdir(parents=True, exist_ok=True)

    encryption_key = settings.ARCHIVE_ENCRYPTION_KEY
    if not encryption_key:
        logger.warning(
            "ARCHIVE_ENCRYPTION_KEY is unset -- archives will be written as "
            "plaintext gzip, readable by anyone with filesystem access. Set "
            "it (see .env.example) to encrypt archived client-IP/domain "
            "history at rest."
        )

    async with AsyncSessionLocal() as session:
        for source in settings.effective_log_sources:
            existing_run = await session.get(ArchiveRun, source.branch)
            since = min(default_since, existing_run.archived_until) if existing_run else default_since

            base_filename = f"squid-events-{source.branch}-{since.date()}_{now.date()}.csv.gz"
            filename = f"{base_filename}.enc" if encryption_key else base_filename
            path = output_dir / filename
            # Write to a temp path and only rename into place once the whole
            # export (and, if enabled, its encryption) has completed
            # successfully -- a crash or a full disk mid-write must never
            # leave a truncated/corrupt file sitting under the real
            # filename, since that's indistinguishable from a good archive
            # until someone actually opens it (same reasoning as
            # log_tailer.py's state-file persistence). Named off
            # base_filename, not filename, so it never itself ends in
            # ".csv.gz" or ".csv.gz.enc" and can't be mistaken for a
            # finished archive if a crash leaves it behind.
            tmp_path = output_dir / f"{base_filename}.tmp"

            # row_counter is incremented by stream_csv itself, once per
            # actual row written -- counting "\r\n" occurrences in the
            # output text instead (as this used to) overcounts whenever a
            # field's raw value contains a literal "\r\n" byte pair (Squid
            # can log raw control bytes verbatim from a malformed request
            # URL, see log_tailer.py's docstring), since csv.writer quotes
            # such a field rather than stripping it.
            row_counter: list[int] = [0]
            with gzip.open(tmp_path, "wt", encoding="utf-8", newline="") as f:
                async for chunk in stream_csv(
                    session, since, now, blocked_only=False, branch=source.branch, row_counter=row_counter
                ):
                    f.write(chunk)
            row_count = row_counter[0]

            if encryption_key:
                # Fernet tokens aren't chunkable, so this is one extra pass
                # over the already-gzipped bytes rather than streamed inline
                # above -- see the module docstring's "Encryption at rest"
                # section for why that's the right tradeoff here.
                plaintext = tmp_path.read_bytes()
                tmp_path.write_bytes(Fernet(encryption_key.encode()).encrypt(plaintext))
            os.replace(tmp_path, path)  # atomic on POSIX

            logger.info(
                "Archived raw events",
                extra={
                    "branch": source.branch,
                    "row_count": row_count,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "encrypted": encryption_key is not None,
                },
            )

            if existing_run is not None:
                existing_run.archived_until = now
            else:
                session.add(ArchiveRun(branch=source.branch, archived_until=now))
            await session.commit()

    _purge_old_archives(output_dir, keep_days)
