import asyncio
import json
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.raw_event import RawEvent
from app.schemas.common import RangeParam
from app.services import export_job_service


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


async def test_run_job_writes_csv_and_marks_done(db_session: AsyncSession, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(5)])
    await db_session.commit()

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
    )
    assert job.status == ExportJobStatus.PENDING

    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.DONE
    assert refreshed.row_count == 5
    assert refreshed.file_path is not None
    assert refreshed.file_path.endswith(".zip")  # raw .csv is zipped and removed, see run_job
    with zipfile.ZipFile(refreshed.file_path) as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert names[0] == export_job_service.inner_filename(refreshed)
        csv_text = zf.read(names[0]).decode()
    assert csv_text.count("\n") == 6  # header + 5 rows
    assert refreshed.file_size_bytes == Path(refreshed.file_path).stat().st_size
    assert refreshed.file_size_bytes > 0


async def test_create_job_records_export_created_audit_entry(db_session: AsyncSession):
    # Exporting raw traffic data is security-relevant the same way
    # user-management changes are (see create_job's comment) -- an admin
    # needs to be able to answer "who exported what, and when."
    since = RangeParam.ONE_HOUR.since()
    until = datetime.now(UTC)
    await export_job_service.create_job(db_session, since, until, "csv", True, "default", "actor-123")

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EXPORT_CREATED)
        )
    ).scalar_one()
    assert entry.actor_user_id == "actor-123"
    assert entry.target_user_id is None  # not about another account
    assert "format=csv" in entry.detail
    assert "blocked_only=True" in entry.detail
    assert "branch=default" in entry.detail


async def test_run_job_writes_valid_json(db_session: AsyncSession, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(3)])
    await db_session.commit()

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "json", False, None, "test-admin"
    )
    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.DONE
    with zipfile.ZipFile(refreshed.file_path) as zf:
        parsed = json.loads(zf.read(export_job_service.inner_filename(refreshed)))
    assert len(parsed) == 3


async def test_run_job_commits_progress_while_running(db_engine, tmp_path: Path, monkeypatch):
    # A wide range at real traffic volumes can take minutes; before this,
    # row_count stayed null for the entire RUNNING phase and only got set
    # once at the very end, so a client polling GET /export/jobs/{id} had
    # nothing to show for however long that took. Uses its own session
    # factory (rather than the single shared db_session other tests reuse)
    # specifically so the mid-run read below goes through a genuinely
    # separate session -- proving the progress update was actually
    # committed to the database, not just held in run_job's own session.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", session_factory)

    async with session_factory() as setup_session:
        job = await export_job_service.create_job(
            setup_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
        )
    job_id = job.id

    # Forces every elapsed-time check in run_job's streaming loop to see
    # >= 1s having passed, so the (normally once-a-second) throttled commit
    # fires after every batch instead of only once at the very end.
    fake_clock = {"t": 0.0}

    def fake_monotonic() -> float:
        fake_clock["t"] += 2.0
        return fake_clock["t"]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    mid_run_row_count = None

    async def _fake_stream(*args, **kwargs):
        row_counter = args[-1]
        row_counter[0] = 42
        yield "id,domain\n"

        nonlocal mid_run_row_count
        async with session_factory() as reader:
            mid_run_row_count = (await reader.get(ExportJob, job_id)).row_count

        row_counter[0] = 100
        yield "more,data\n"

    monkeypatch.setattr(export_job_service, "stream_csv", _fake_stream)

    await export_job_service.run_job(job_id)

    assert mid_run_row_count == 42  # visible to another session before the job finished

    async with session_factory() as verify_session:
        refreshed = await verify_session.get(ExportJob, job_id)
    assert refreshed.status == ExportJobStatus.DONE
    assert refreshed.row_count == 100


async def test_run_job_honors_cancellation_requested_while_pending(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
    )
    # Simulates a cancel request landing before run_job's task even starts --
    # request_cancellation only ever touches the in-memory flag, never the
    # job row itself, so nothing else needs to happen first.
    export_job_service.request_cancellation(job.id)

    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.CANCELLED
    assert list(tmp_path.iterdir()) == []  # never even started writing


async def test_run_job_honors_cancellation_requested_mid_stream(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    # Unlike the PENDING case above, this must clean up whatever partial
    # file streaming had already flushed before the cancellation checkpoint
    # was reached -- the same failure mode test_run_job_deletes_partial_file
    # _on_mid_stream_failure covers for an actual error.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
    )

    async def _fake_stream(*args, **kwargs):
        row_counter = args[-1]
        row_counter[0] = 7
        yield "id,domain\n"
        # request_cancellation is normally called from the cancel route
        # while run_job is mid-flight elsewhere -- from inside the fake
        # stream is the simplest way to land it exactly between batches.
        export_job_service.request_cancellation(job.id)
        yield "more,data\n"

    monkeypatch.setattr(export_job_service, "stream_csv", _fake_stream)

    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.CANCELLED
    assert refreshed.row_count == 7  # whatever had been written before the flag was seen
    assert list(tmp_path.iterdir()) == []  # partial file cleaned up, same as a genuine failure


async def test_run_job_marks_failed_on_error(db_session: AsyncSession, monkeypatch):
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)
    # No _jobs_dir patch -- the real EXPORT_JOBS_DIR default ("./export_jobs")
    # is harmless to create, so force a different failure instead: an
    # unwritable directory path.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: Path("/nonexistent/definitely/not/here"))

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
    )
    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.FAILED
    assert refreshed.error_message


async def test_run_job_deletes_partial_file_on_mid_stream_failure(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    # A failure that happens *after* some chunks were already flushed to
    # disk (unlike test_run_job_marks_failed_on_error above, which fails
    # before ever opening the file) used to leave a truncated file behind
    # forever: job.file_path is only ever set on the success path, so
    # purge_old_jobs (which only unlinks via job.file_path) could never
    # find it.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    async def _broken_stream(*args, **kwargs):
        yield "id,domain\n"
        raise RuntimeError("simulated mid-stream failure")

    monkeypatch.setattr(export_job_service, "stream_csv", _broken_stream)

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), "csv", False, None, "test-admin"
    )
    await export_job_service.run_job(job.id)

    refreshed = await db_session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.FAILED
    assert list(tmp_path.iterdir()) == []


async def test_reconcile_orphaned_jobs_fails_stale_pending_and_running_jobs(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    # Simulates what a crash/restart mid-export leaves behind: rows stuck in
    # PENDING/RUNNING with no asyncio task left anywhere to ever move them
    # forward (the one that would have belonged to the previous process),
    # plus the partial file the interrupted run_job had started writing.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    import app.models.db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)

    now = datetime.now(UTC)
    orphaned_running_file = tmp_path / "orphaned-running.csv"
    orphaned_running_file.write_text("id,domain\n1,example.com\n")
    db_session.add_all(
        [
            ExportJob(
                id="orphaned-pending",
                status=ExportJobStatus.PENDING,
                format="csv",
                since=now - timedelta(hours=1),
                until=now,
                blocked_only=False,
                branch=None,
                created_at=now,
            ),
            ExportJob(
                id="orphaned-running",
                status=ExportJobStatus.RUNNING,
                format="csv",
                since=now - timedelta(hours=1),
                until=now,
                blocked_only=False,
                branch=None,
                created_at=now,
            ),
            ExportJob(
                id="already-done",
                status=ExportJobStatus.DONE,
                format="csv",
                since=now - timedelta(hours=1),
                until=now,
                blocked_only=False,
                branch=None,
                file_path=str(tmp_path / "already-done.csv"),
                row_count=0,
                created_at=now,
                completed_at=now,
            ),
        ]
    )
    await db_session.commit()

    reconciled_count = await export_job_service.reconcile_orphaned_jobs()

    assert reconciled_count == 2
    pending = await db_session.get(ExportJob, "orphaned-pending")
    running = await db_session.get(ExportJob, "orphaned-running")
    done = await db_session.get(ExportJob, "already-done")
    assert pending.status == ExportJobStatus.FAILED
    assert running.status == ExportJobStatus.FAILED
    assert running.error_message
    assert done.status == ExportJobStatus.DONE  # untouched
    assert not orphaned_running_file.exists()


async def test_purge_old_jobs_deletes_expired_rows_and_files(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    old_file = tmp_path / "old.csv"
    old_file.write_text("id,domain\n")
    recent_file = tmp_path / "recent.csv"
    recent_file.write_text("id,domain\n")

    now = datetime.now(UTC)
    db_session.add_all(
        [
            ExportJob(
                id="old-job",
                status=ExportJobStatus.DONE,
                format="csv",
                since=now - timedelta(days=1),
                until=now,
                blocked_only=False,
                branch=None,
                file_path=str(old_file),
                created_at=now - timedelta(hours=49),
            ),
            ExportJob(
                id="recent-job",
                status=ExportJobStatus.DONE,
                format="csv",
                since=now - timedelta(days=1),
                until=now,
                blocked_only=False,
                branch=None,
                file_path=str(recent_file),
                created_at=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()

    deleted_count = await export_job_service.purge_old_jobs(db_session)
    await db_session.commit()

    assert deleted_count == 1
    assert await db_session.get(ExportJob, "old-job") is None
    assert await db_session.get(ExportJob, "recent-job") is not None
    assert not old_file.exists()
    assert recent_file.exists()


async def test_create_export_job_route_returns_pending(
    app_client: AsyncClient, admin_token, auth_headers, tmp_path: Path, monkeypatch
):
    # Keeps the real background task (still fired for real here) from
    # writing into the repo's working directory during the test.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)

    response = await app_client.post(
        "/api/export/jobs?format=csv", headers=auth_headers(admin_token)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] in ("pending", "running", "done")  # the real background task may race ahead
    assert body["format"] == "csv"


async def test_download_export_job_route_records_audit_entry(
    app_client: AsyncClient, admin_token, auth_headers, tmp_path: Path, monkeypatch, db_session: AsyncSession
):
    # EXPORT_CREATED (see test_create_job_records_export_created_audit_entry
    # above) only proves someone queued the export -- jobs are visible to
    # every admin, not just whoever created them, so this is the entry that
    # proves who actually pulled the finished file down.
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)

    create_response = await app_client.post(
        "/api/export/jobs?range=1h&format=csv", headers=auth_headers(admin_token)
    )
    job_id = create_response.json()["id"]

    for _ in range(20):
        status_response = await app_client.get(
            f"/api/export/jobs/{job_id}", headers=auth_headers(admin_token)
        )
        if status_response.json()["status"] == "done":
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("export job never reached done")

    download_response = await app_client.get(
        f"/api/export/jobs/{job_id}/download", headers=auth_headers(admin_token)
    )
    assert download_response.status_code == 200

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EXPORT_DOWNLOADED)
        )
    ).scalar_one()
    assert entry.actor_email == "admin@example.com"
    assert f"job_id={job_id}" in entry.detail


async def test_download_export_job_route_409_does_not_record_audit_entry(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch, db_session: AsyncSession
):
    # The 409-before-done case (see test_download_export_job_route_409_
    # before_done below) never actually serves the file -- nothing was
    # downloaded, so nothing should be audited.
    monkeypatch.setattr(export_job_service, "start", lambda job_id: None)

    create_response = await app_client.post(
        "/api/export/jobs?format=csv", headers=auth_headers(admin_token)
    )
    job_id = create_response.json()["id"]

    response = await app_client.get(
        f"/api/export/jobs/{job_id}/download", headers=auth_headers(admin_token)
    )
    assert response.status_code == 409

    count = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EXPORT_DOWNLOADED)
        )
    ).scalars().all()
    assert count == []


async def test_get_export_job_route_404_for_unknown_id(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/export/jobs/does-not-exist", headers=auth_headers(admin_token))
    assert response.status_code == 404


async def test_download_export_job_route_409_before_done(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    # Prevent the real background task from racing to completion during
    # the test, so the job is deterministically still PENDING/RUNNING.
    monkeypatch.setattr(export_job_service, "start", lambda job_id: None)

    create_response = await app_client.post(
        "/api/export/jobs?format=csv", headers=auth_headers(admin_token)
    )
    job_id = create_response.json()["id"]

    response = await app_client.get(
        f"/api/export/jobs/{job_id}/download", headers=auth_headers(admin_token)
    )
    assert response.status_code == 409


async def test_cancel_export_job_route_marks_job_cancelled(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    # Prevent the real background task from racing to completion, same as
    # test_download_export_job_route_409_before_done above -- keeps the job
    # deterministically PENDING so the cancel endpoint's own effect (not a
    # race with run_job finishing on its own) is what's being tested.
    monkeypatch.setattr(export_job_service, "start", lambda job_id: None)

    create_response = await app_client.post(
        "/api/export/jobs?format=csv", headers=auth_headers(admin_token)
    )
    job_id = create_response.json()["id"]

    cancel_response = await app_client.post(
        f"/api/export/jobs/{job_id}/cancel", headers=auth_headers(admin_token)
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "pending"  # cancellation is async -- see the route's docstring

    # Actually running run_job now (start() was stubbed out above) proves
    # the cancel request was recorded and gets honored once the job's own
    # task next checks for it -- immediately, since it's still PENDING.
    await export_job_service.run_job(job_id)
    status_response = await app_client.get(
        f"/api/export/jobs/{job_id}", headers=auth_headers(admin_token)
    )
    assert status_response.json()["status"] == "cancelled"


async def test_cancel_export_job_route_409_when_already_done(
    app_client: AsyncClient, admin_token, auth_headers
):
    create_response = await app_client.post(
        "/api/export/jobs?range=1h&format=csv", headers=auth_headers(admin_token)
    )
    job_id = create_response.json()["id"]
    # No data in range -- the real background task (still fired for real
    # here) reaches DONE almost immediately.
    for _ in range(20):
        status_response = await app_client.get(
            f"/api/export/jobs/{job_id}", headers=auth_headers(admin_token)
        )
        if status_response.json()["status"] == "done":
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("export job never reached done")

    cancel_response = await app_client.post(
        f"/api/export/jobs/{job_id}/cancel", headers=auth_headers(admin_token)
    )
    assert cancel_response.status_code == 409


async def test_cancel_export_job_route_404_for_unknown_id(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post(
        "/api/export/jobs/does-not-exist/cancel", headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


async def test_list_export_jobs_route_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/export/jobs", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_create_export_job_route_429_at_max_concurrent(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    # Nothing else caps how many exports can run at once, and each can be a
    # multi-hundred-MB file running for minutes -- without this, several
    # tabs/admins kicking off wide-range exports at the same time could fill
    # the disk. Keeps jobs stuck PENDING (like test_download_..._409_before_done
    # above) so hitting the default EXPORT_JOB_MAX_CONCURRENT (3) is deterministic.
    monkeypatch.setattr(export_job_service, "start", lambda job_id: None)

    for _ in range(3):
        response = await app_client.post("/api/export/jobs?format=csv", headers=auth_headers(admin_token))
        assert response.status_code == 201

    response = await app_client.post("/api/export/jobs?format=csv", headers=auth_headers(admin_token))
    assert response.status_code == 429
