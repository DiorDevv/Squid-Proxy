"""Tests for app.services.archive_service.archive -- previously untested
(it lived only as scripts/archive_weekly_export.py's inline logic)."""

import gzip
import io
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.archive_run import ArchiveRun
from app.models.raw_event import RawEvent
from app.services import archive_service


def _make_event(**overrides) -> RawEvent:
    defaults = dict(
        timestamp=datetime.now(UTC),
        duration_ms=1,
        client_ip="10.0.0.1",
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        user="alice",
        hierarchy="HIER_DIRECT",
        peer=None,
        content_type="text/html",
        blocked=False,
    )
    defaults.update(overrides)
    return RawEvent(**defaults)


def _patch(monkeypatch, db_session: AsyncSession, settings: Settings | None = None) -> None:
    monkeypatch.setattr(archive_service, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(archive_service, "get_settings", lambda: settings or Settings())


async def test_archive_writes_gzip_csv_and_upserts_archive_run(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    _patch(monkeypatch, db_session)

    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(3)])
    await db_session.commit()

    await archive_service.archive(tmp_path, keep_days=365)

    files = list(tmp_path.glob("squid-events-default-*.csv.gz"))
    assert len(files) == 1
    with gzip.open(files[0], "rt", newline="") as f:
        content = f.read()
    assert content.count("\r\n") == 4  # header + 3 rows

    run = await db_session.get(ArchiveRun, "default")
    assert run is not None
    assert (datetime.now(UTC) - run.archived_until) < timedelta(seconds=5)

    # The temp file used for the atomic write/rename must never survive a
    # successful run.
    assert list(tmp_path.glob("*.tmp")) == []


async def test_archive_extends_back_further_when_a_run_was_missed(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    # A missed run's recovery must not silently skip the gap between "7 days
    # ago" and wherever the last successful run actually left off -- see
    # archive_service's module docstring. Uses 10 days ago specifically
    # (older than the flat 7-day default window) so `since` is forced to
    # extend back further than usual, rather than the normal case where a
    # recent prior run makes no difference to the (always-at-least-7-days)
    # window.
    _patch(monkeypatch, db_session)

    prior_archived_until = datetime.now(UTC) - timedelta(days=10)
    db_session.add(ArchiveRun(branch="default", archived_until=prior_archived_until))
    await db_session.commit()

    await archive_service.archive(tmp_path, keep_days=365)

    files = list(tmp_path.glob("squid-events-default-*.csv.gz"))
    assert len(files) == 1
    # Filename encodes the since date -- 10 days ago, not the flat 7-day default.
    assert prior_archived_until.date().isoformat() in files[0].name

    run = await db_session.get(ArchiveRun, "default")
    assert run.archived_until > prior_archived_until


async def test_archive_purges_files_older_than_keep_days(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    _patch(monkeypatch, db_session)

    old_file = tmp_path / "squid-events-default-2020-01-01_2020-01-08.csv.gz"
    old_file.write_bytes(b"")
    old_mtime = (datetime.now(UTC) - timedelta(days=400)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))

    await archive_service.archive(tmp_path, keep_days=365)

    assert not old_file.exists()
    # This run's own fresh archive must survive its own purge pass.
    assert list(tmp_path.glob("squid-events-default-*.csv.gz"))


async def test_archive_encrypts_when_key_configured(db_session: AsyncSession, tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode()
    _patch(monkeypatch, db_session, Settings(ARCHIVE_ENCRYPTION_KEY=key))

    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(3)])
    await db_session.commit()

    await archive_service.archive(tmp_path, keep_days=365)

    # Written as .csv.gz.enc, not plain .csv.gz -- an encrypted archive must
    # never be mistaken for a plain one (or vice versa) by filename alone.
    plain_files = list(tmp_path.glob("squid-events-default-*.csv.gz"))
    assert plain_files == []
    encrypted_files = list(tmp_path.glob("squid-events-default-*.csv.gz.enc"))
    assert len(encrypted_files) == 1

    # The on-disk bytes must actually be ciphertext, not a plaintext gzip
    # stream with ".enc" just tacked onto the filename.
    ciphertext = encrypted_files[0].read_bytes()
    assert not ciphertext.startswith(b"\x1f\x8b")  # gzip magic bytes

    # ...but round-trips back to the same CSV content a plain archive
    # would have held, via the same decrypt path scripts/decrypt_archive.py
    # uses.
    plaintext_gzip = Fernet(key.encode()).decrypt(ciphertext)
    with gzip.open(io.BytesIO(plaintext_gzip), "rt", newline="") as f:
        content = f.read()
    assert content.count("\r\n") == 4  # header + 3 rows

    assert list(tmp_path.glob("*.tmp")) == []


async def test_archive_purges_old_encrypted_files(db_session: AsyncSession, tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode()
    _patch(monkeypatch, db_session, Settings(ARCHIVE_ENCRYPTION_KEY=key))

    old_file = tmp_path / "squid-events-default-2020-01-01_2020-01-08.csv.gz.enc"
    old_file.write_bytes(b"")
    old_mtime = (datetime.now(UTC) - timedelta(days=400)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))

    await archive_service.archive(tmp_path, keep_days=365)

    assert not old_file.exists()
    assert list(tmp_path.glob("squid-events-default-*.csv.gz.enc"))
