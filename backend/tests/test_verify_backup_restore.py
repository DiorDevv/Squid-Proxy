"""Tests for scripts/verify_backup_restore.py. Mocks subprocess.run
throughout -- these check that the right commands get built, that the
throwaway database/tmp file is always cleaned up (even on failure), and
that a failure reaches notify_operator_failure -- not that a real
pg_restore/sqlite3 binary actually runs (covered by the real, manual
verification against squidproxy-postgres-1's actual backups instead, same
convention as test_backup_database.py's own docstring)."""

import subprocess

import pytest

from app.core.config import Settings
from scripts import verify_backup_restore


def test_find_latest_backup_picks_the_newest_file(tmp_path):
    import os
    from datetime import UTC, datetime, timedelta

    old = tmp_path / "squid-dashboard-backup-20200101T000000Z.dump"
    old.write_bytes(b"")
    old_mtime = (datetime.now(UTC) - timedelta(days=10)).timestamp()
    os.utime(old, (old_mtime, old_mtime))

    newest = tmp_path / "squid-dashboard-backup-20260101T000000Z.dump"
    newest.write_bytes(b"")

    assert verify_backup_restore._find_latest_backup(tmp_path) == newest


def test_find_latest_backup_raises_when_none_found(tmp_path):
    with pytest.raises(verify_backup_restore.BackupVerificationError, match="No backup files found"):
        verify_backup_restore._find_latest_backup(tmp_path)


def test_verify_postgres_creates_restores_sanity_checks_and_drops_the_throwaway_db(monkeypatch, tmp_path):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "psql" and "SELECT count" in " ".join(args):
            return subprocess.CompletedProcess(args, 0, stdout="3\n")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(verify_backup_restore.subprocess, "run", _fake_run)

    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.dump"
    backup_file.write_bytes(b"")

    row_count = verify_backup_restore._verify_postgres(
        "postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard", backup_file
    )

    assert row_count == 3
    commands = [args[0] for args in calls]
    assert commands[0] == "psql"  # CREATE DATABASE
    assert "CREATE DATABASE" in " ".join(calls[0])
    assert any(args[0] == "pg_restore" for args in calls)
    assert any("SELECT count" in " ".join(args) for args in calls if args[0] == "psql")
    assert "DROP DATABASE" in " ".join(calls[-1])  # always dropped, last call


def test_verify_postgres_drops_the_throwaway_db_even_when_pg_restore_fails(monkeypatch, tmp_path):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "pg_restore":
            raise subprocess.CalledProcessError(1, args, stderr="corrupt dump")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(verify_backup_restore.subprocess, "run", _fake_run)

    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.dump"
    backup_file.write_bytes(b"")

    with pytest.raises(verify_backup_restore.BackupVerificationError, match="pg_restore"):
        verify_backup_restore._verify_postgres(
            "postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard", backup_file
        )

    assert "DROP DATABASE" in " ".join(calls[-1])


def test_verify_sqlite_runs_integrity_check_and_sanity_query(monkeypatch, tmp_path):
    calls = []

    def _fake_run(args, **kwargs):
        calls.append(args)
        if "integrity_check" in " ".join(args):
            return subprocess.CompletedProcess(args, 0, stdout="ok\n")
        return subprocess.CompletedProcess(args, 0, stdout="2\n")

    monkeypatch.setattr(verify_backup_restore.subprocess, "run", _fake_run)

    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.db"
    backup_file.write_bytes(b"fake-sqlite-bytes")
    tmp_target = tmp_path / "restore_verify_tmp.db"

    row_count = verify_backup_restore._verify_sqlite(backup_file, tmp_target)

    assert row_count == 2
    assert not tmp_target.exists()  # cleaned up


def test_verify_sqlite_raises_and_cleans_up_on_failed_integrity_check(monkeypatch, tmp_path):
    def _fake_run(args, **kwargs):
        if "integrity_check" in " ".join(args):
            return subprocess.CompletedProcess(args, 0, stdout="database disk image is malformed\n")
        return subprocess.CompletedProcess(args, 0, stdout="0\n")

    monkeypatch.setattr(verify_backup_restore.subprocess, "run", _fake_run)

    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.db"
    backup_file.write_bytes(b"fake-sqlite-bytes")
    tmp_target = tmp_path / "restore_verify_tmp.db"

    with pytest.raises(verify_backup_restore.BackupVerificationError, match="Integrity check failed"):
        verify_backup_restore._verify_sqlite(backup_file, tmp_target)

    assert not tmp_target.exists()  # cleaned up even on failure


def test_run_picks_postgres_backend_from_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        verify_backup_restore,
        "get_settings",
        lambda: Settings(DATABASE_URL="postgresql+asyncpg://squid:pw@postgres:5432/squid_dashboard"),
    )
    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.dump"
    backup_file.write_bytes(b"")

    calls = []
    monkeypatch.setattr(
        verify_backup_restore, "_verify_postgres", lambda url, f: calls.append(f) or 1
    )
    monkeypatch.setattr(
        verify_backup_restore, "_verify_sqlite", lambda f, tmp: pytest.fail("wrong backend")
    )

    verify_backup_restore.run(tmp_path, backup_file)

    assert calls == [backup_file]


def test_run_rejects_an_unsupported_database_url_scheme(monkeypatch, tmp_path):
    monkeypatch.setattr(verify_backup_restore, "get_settings", lambda: Settings(DATABASE_URL="mysql://x"))
    backup_file = tmp_path / "squid-dashboard-backup-20260101T000000Z.dump"
    backup_file.write_bytes(b"")

    with pytest.raises(verify_backup_restore.BackupVerificationError, match="Unsupported DATABASE_URL"):
        verify_backup_restore.run(tmp_path, backup_file)


def test_main_notifies_operator_on_verification_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        verify_backup_restore,
        "run",
        lambda output_dir, backup_file: (_ for _ in ()).throw(
            verify_backup_restore.BackupVerificationError("sanity check failed")
        ),
    )
    notify_calls = []

    async def _fake_notify(source, message):
        notify_calls.append((source, message))

    monkeypatch.setattr(verify_backup_restore, "notify_operator_failure", _fake_notify)
    monkeypatch.setattr(verify_backup_restore.sys, "argv", ["verify_backup_restore.py"])

    with pytest.raises(SystemExit):
        verify_backup_restore.main()

    assert len(notify_calls) == 1
    assert notify_calls[0][0] == "backup_restore_verify"
