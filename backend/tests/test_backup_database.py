"""Tests for scripts/backup_database.py. Mocks subprocess.run throughout --
these check that the right command gets built for the right dialect, not
that a real pg_dump/sqlite3 binary actually runs (covered by the Docker
verification in docker-compose.yml's db-backup service instead)."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import Settings
from scripts import backup_database


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("sqlite+aiosqlite:///./squid_dashboard.db", Path.cwd() / "squid_dashboard.db"),
        ("sqlite+aiosqlite:///relative/path.db", Path.cwd() / "relative/path.db"),
        ("sqlite+aiosqlite:////absolute/path.db", Path("/absolute/path.db")),
    ],
)
def test_sqlite_db_path_handles_relative_and_absolute_urls(database_url, expected):
    assert backup_database._sqlite_db_path(database_url) == expected


def test_sqlite_db_path_rejects_a_url_with_a_host_part():
    with pytest.raises(ValueError, match="unexpected host part"):
        backup_database._sqlite_db_path("sqlite+aiosqlite://somehost/path.db")


def test_backup_postgres_strips_asyncpg_driver_suffix_and_uses_custom_format(monkeypatch, tmp_path):
    calls = []
    kwargs_seen = []
    monkeypatch.setattr(
        backup_database.subprocess,
        "run",
        lambda args, **kwargs: (calls.append(args), kwargs_seen.append(kwargs))
        and subprocess.CompletedProcess(args, 0),
    )

    dest = tmp_path / "backup.dump"
    backup_database._backup_postgres("postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard", dest)

    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "pg_dump"
    assert "--format=custom" in args
    assert f"--file={dest}" in args
    assert "--host" in args and args[args.index("--host") + 1] == "postgres"
    assert "--port" in args and args[args.index("--port") + 1] == "5432"
    assert "--username" in args and args[args.index("--username") + 1] == "squid"
    assert "--dbname=squid_dashboard" in args
    # The password must never appear in argv (visible to other local users
    # via `ps`/`/proc/<pid>/cmdline`) -- only in the subprocess's own env.
    assert not any("pw" in arg for arg in args)
    assert kwargs_seen[0]["env"]["PGPASSWORD"] == "pw"


def test_backup_sqlite_uses_the_online_backup_command(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        backup_database.subprocess,
        "run",
        lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0),
    )

    db_path = tmp_path / "squid_dashboard.db"
    dest = tmp_path / "backup.db"
    backup_database._backup_sqlite(f"sqlite+aiosqlite:///{db_path}", dest)

    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "sqlite3"
    assert args[1] == str(db_path)
    assert f".backup '{dest}'" in args[2]


def test_run_picks_postgres_backend_from_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backup_database,
        "get_settings",
        lambda: Settings(
            DATABASE_URL="postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard"
        ),
    )
    postgres_calls = []

    def _fake_backup_postgres(url, dest):
        postgres_calls.append(dest)
        dest.write_bytes(b"")  # real _backup_postgres produces a file at dest

    monkeypatch.setattr(backup_database, "_backup_postgres", _fake_backup_postgres)
    monkeypatch.setattr(backup_database, "_backup_sqlite", lambda url, dest: pytest.fail("wrong backend"))

    backup_database.run(tmp_path, keep_days=30)

    assert len(postgres_calls) == 1
    assert postgres_calls[0].name.startswith("squid-dashboard-backup-")
    assert postgres_calls[0].suffix == ".dump"


def test_run_picks_sqlite_backend_from_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backup_database, "get_settings", lambda: Settings(DATABASE_URL="sqlite+aiosqlite:///./db.sqlite3")
    )
    sqlite_calls = []

    def _fake_backup_sqlite(url, dest):
        sqlite_calls.append(dest)
        dest.write_bytes(b"")  # real _backup_sqlite produces a file at dest

    monkeypatch.setattr(backup_database, "_backup_sqlite", _fake_backup_sqlite)
    monkeypatch.setattr(backup_database, "_backup_postgres", lambda url, dest: pytest.fail("wrong backend"))

    backup_database.run(tmp_path, keep_days=30)

    assert len(sqlite_calls) == 1
    assert sqlite_calls[0].suffix == ".db"


def test_run_rejects_an_unsupported_database_url_scheme(monkeypatch, tmp_path):
    monkeypatch.setattr(backup_database, "get_settings", lambda: Settings(DATABASE_URL="mysql://x"))

    with pytest.raises(ValueError, match="Unsupported DATABASE_URL scheme"):
        backup_database.run(tmp_path, keep_days=30)


def test_run_deletes_partial_backup_file_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backup_database,
        "get_settings",
        lambda: Settings(DATABASE_URL="sqlite+aiosqlite:///./db.sqlite3"),
    )

    def _fake_backup_sqlite(url, dest):
        # A real pg_dump/sqlite3 invocation that fails partway through can
        # still have written some bytes to dest before raising.
        dest.write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, ["sqlite3"], stderr="boom")

    monkeypatch.setattr(backup_database, "_backup_sqlite", _fake_backup_sqlite)

    with pytest.raises(subprocess.CalledProcessError):
        backup_database.run(tmp_path, keep_days=30)

    assert list(tmp_path.glob("squid-dashboard-backup-*")) == []


def test_prune_old_backups_deletes_files_older_than_keep_days(tmp_path):
    old_file = tmp_path / "squid-dashboard-backup-20200101T000000Z.dump"
    old_file.write_bytes(b"")
    old_mtime = (datetime.now(UTC) - timedelta(days=60)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))

    recent_file = tmp_path / "squid-dashboard-backup-recent.dump"
    recent_file.write_bytes(b"")

    backup_database._prune_old_backups(tmp_path, keep_days=30)

    assert not old_file.exists()
    assert recent_file.exists()
