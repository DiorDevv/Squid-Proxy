"""Tests for scripts/offsite_sync.py. Mocks subprocess.run / shutil.which
throughout -- these check that the right restic commands get built and that
the misconfiguration / failure paths alert rather than pass silently, not
that a real restic binary runs (the Docker db-offsite service covers that
end to end)."""

import subprocess

import pytest

from app.core.config import Settings
from scripts import offsite_sync


@pytest.fixture(autouse=True)
def _clean_offsite_env(monkeypatch):
    for key in (
        "OFFSITE_ENABLED",
        "RESTIC_REPOSITORY",
        "OFFSITE_RESTIC_REPOSITORY",
        "RESTIC_PASSWORD",
        "RESTIC_PASSWORD_FILE",
        "OFFSITE_RESTIC_PASSWORD",
        "OFFSITE_RESTIC_PASSWORD_FILE",
        "OFFSITE_PATHS",
        "OFFSITE_KEEP_DAILY",
        "OFFSITE_KEEP_WEEKLY",
        "OFFSITE_KEEP_MONTHLY",
    ):
        monkeypatch.delenv(key, raising=False)


def _record_restic(monkeypatch, *, config_exists=True):
    """Patch subprocess.run so restic invocations are recorded instead of
    run. `restic cat config` returns rc=0/1 per config_exists; everything
    else succeeds."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        rc = 0
        if args[:3] == ["restic", "cat", "config"] and not config_exists:
            rc = 1
        return subprocess.CompletedProcess(args, rc, stdout="", stderr="")

    monkeypatch.setattr(offsite_sync.subprocess, "run", fake_run)
    monkeypatch.setattr(offsite_sync.shutil, "which", lambda _: "/usr/bin/restic")
    return calls


def test_restic_env_maps_offsite_aliases_onto_bare_names(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "s3:s3.example.com/bucket/squid")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "hunter2")

    env = offsite_sync.restic_env()

    assert env["RESTIC_REPOSITORY"] == "s3:s3.example.com/bucket/squid"
    assert env["RESTIC_PASSWORD"] == "hunter2"


def test_restic_env_prefers_password_file_alias_over_literal(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD_FILE", "/run/secrets/restic-pw")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "ignored-when-file-present")

    env = offsite_sync.restic_env()

    assert env["RESTIC_PASSWORD_FILE"] == "/run/secrets/restic-pw"
    assert "RESTIC_PASSWORD" not in env


def test_restic_env_requires_a_repository(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    with pytest.raises(ValueError, match="No restic repository configured"):
        offsite_sync.restic_env()


def test_restic_env_requires_a_password(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    with pytest.raises(ValueError, match="No restic repository password"):
        offsite_sync.restic_env()


def test_is_disabled_only_on_explicit_false(monkeypatch):
    assert offsite_sync.is_disabled() is False
    monkeypatch.setenv("OFFSITE_ENABLED", "true")
    assert offsite_sync.is_disabled() is False
    monkeypatch.setenv("OFFSITE_ENABLED", "  FALSE  ")
    assert offsite_sync.is_disabled() is True


def test_resolve_paths_defaults_to_backup_dir_and_archive_dir(monkeypatch, tmp_path):
    backups = tmp_path / "backups"
    archives = tmp_path / "archives"
    backups.mkdir()
    archives.mkdir()
    monkeypatch.setattr(
        offsite_sync,
        "get_settings",
        lambda: Settings(ARCHIVE_OUTPUT_DIR=str(archives)),
    )

    assert offsite_sync.resolve_paths(backups) == [backups, archives]


def test_resolve_paths_skips_missing_paths(monkeypatch, tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(
        offsite_sync,
        "get_settings",
        lambda: Settings(ARCHIVE_OUTPUT_DIR=str(tmp_path / "does-not-exist")),
    )

    assert offsite_sync.resolve_paths(backups) == [backups]


def test_resolve_paths_honours_explicit_offsite_paths_env(monkeypatch, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("OFFSITE_PATHS", f"{a} {b}")

    assert offsite_sync.resolve_paths(tmp_path / "unused") == [a, b]


def test_ensure_initialised_is_a_noop_when_repo_already_exists(monkeypatch):
    calls = _record_restic(monkeypatch, config_exists=True)
    offsite_sync.ensure_initialised({"RESTIC_REPOSITORY": "r"})
    assert calls == [["restic", "cat", "config"]]


def test_ensure_initialised_inits_a_missing_repo(monkeypatch):
    calls = _record_restic(monkeypatch, config_exists=False)
    offsite_sync.ensure_initialised({"RESTIC_REPOSITORY": "r"})
    assert ["restic", "init"] in calls


def test_ensure_initialised_raises_when_init_also_fails(monkeypatch):
    def fake_run(args, **kwargs):
        # cat config fails (missing repo *or* wrong password), and so does init.
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="denied")

    monkeypatch.setattr(offsite_sync.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        offsite_sync.ensure_initialised({"RESTIC_REPOSITORY": "r"})


def test_sync_builds_tagged_backup_and_forget_commands(monkeypatch, tmp_path):
    backups = tmp_path / "backups"
    archives = tmp_path / "archives"
    backups.mkdir()
    archives.mkdir()
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    monkeypatch.setattr(offsite_sync, "get_settings", lambda: Settings(ARCHIVE_OUTPUT_DIR=str(archives)))
    calls = _record_restic(monkeypatch, config_exists=True)

    offsite_sync.sync(backups, keep_daily=7, keep_weekly=8, keep_monthly=12)

    backup_cmd = next(c for c in calls if c[:2] == ["restic", "backup"])
    assert backup_cmd[2:4] == ["--tag", "squid-watch"]
    assert str(backups) in backup_cmd and str(archives) in backup_cmd

    forget_cmd = next(c for c in calls if c[:2] == ["restic", "forget"])
    assert "--prune" in forget_cmd
    assert forget_cmd[forget_cmd.index("--keep-daily") + 1] == "7"
    assert forget_cmd[forget_cmd.index("--keep-weekly") + 1] == "8"
    assert forget_cmd[forget_cmd.index("--keep-monthly") + 1] == "12"


def test_sync_raises_when_restic_is_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    monkeypatch.setattr(offsite_sync.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="restic not found on PATH"):
        offsite_sync.sync(tmp_path, keep_daily=7, keep_weekly=8, keep_monthly=12)


def test_sync_raises_when_no_paths_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    monkeypatch.setenv("OFFSITE_PATHS", str(tmp_path / "nope"))
    _record_restic(monkeypatch, config_exists=True)

    with pytest.raises(RuntimeError, match="No existing paths"):
        offsite_sync.sync(tmp_path, keep_daily=7, keep_weekly=8, keep_monthly=12)


def test_check_runs_restic_check(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    calls = _record_restic(monkeypatch, config_exists=True)

    offsite_sync.check()

    assert ["restic", "check"] in calls


def test_main_exits_zero_and_runs_nothing_when_disabled(monkeypatch):
    monkeypatch.setenv("OFFSITE_ENABLED", "false")
    monkeypatch.setattr(offsite_sync.sys, "argv", ["offsite_sync.py"])
    monkeypatch.setattr(offsite_sync, "sync", lambda *a, **k: pytest.fail("sync ran while disabled"))

    offsite_sync.main()  # returns, no SystemExit


def test_main_alerts_and_exits_nonzero_on_misconfiguration(monkeypatch):
    monkeypatch.setattr(offsite_sync.sys, "argv", ["offsite_sync.py"])
    notified = []

    async def _capture(source, message, **k):
        notified.append((source, message))

    monkeypatch.setattr(offsite_sync, "notify_operator_failure", _capture)

    with pytest.raises(SystemExit) as exc:
        offsite_sync.main()

    assert exc.value.code == 1
    assert notified and notified[0][0] == "offsite"


def test_main_alerts_with_check_source_on_check_failure(monkeypatch):
    monkeypatch.setenv("OFFSITE_RESTIC_REPOSITORY", "sftp:u@h:/r")
    monkeypatch.setenv("OFFSITE_RESTIC_PASSWORD", "pw")
    monkeypatch.setattr(offsite_sync.sys, "argv", ["offsite_sync.py", "--check"])
    monkeypatch.setattr(offsite_sync.shutil, "which", lambda _: "/usr/bin/restic")

    def fail_check(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr="repo broken")

    monkeypatch.setattr(offsite_sync.subprocess, "run", fail_check)
    notified = []

    async def _capture(source, message, **k):
        notified.append((source, message))

    monkeypatch.setattr(offsite_sync, "notify_operator_failure", _capture)

    with pytest.raises(SystemExit):
        offsite_sync.main()

    assert notified and notified[0][0] == "offsite-check"
