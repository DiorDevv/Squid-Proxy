"""Export manifest + Ed25519 signing (Faza 6.6 / docs/PRODUCT.md #5) --
export_signing.py's crypto in isolation, then run_job's wiring end to end.

export_job_service imports export_signing as a module (`from app.services
import ..., export_signing`), so patching this test file's own
`export_signing.get_settings` reaches run_job's calls too -- same module
object, no need to reach through export_job_service.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import db as db_module
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.raw_event import RawEvent
from app.schemas.common import RangeParam
from app.services import export_job_service, export_signing


def _seed() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _make_event(**overrides) -> RawEvent:
    defaults = dict(
        timestamp=datetime.now(UTC),
        duration_ms=10,
        client_ip="10.0.0.5",
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        blocked=False,
    )
    defaults.update(overrides)
    return RawEvent(**defaults)


# ---- export_signing.py in isolation ----------------------------------


def test_verify_accepts_a_valid_signature(monkeypatch):
    seed = _seed()
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=seed))
    manifest = {"job_id": "abc", "row_count": 5}
    signature = export_signing.sign(manifest)
    public_key = export_signing.public_key_b64()

    assert signature is not None
    assert export_signing.verify(manifest, signature, public_key) is True


def test_verify_rejects_a_tampered_manifest(monkeypatch):
    seed = _seed()
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=seed))
    manifest = {"job_id": "abc", "row_count": 5}
    signature = export_signing.sign(manifest)
    public_key = export_signing.public_key_b64()

    assert export_signing.verify({"job_id": "abc", "row_count": 999}, signature, public_key) is False


def test_verify_rejects_the_wrong_public_key(monkeypatch):
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=_seed()))
    manifest = {"job_id": "abc"}
    signature = export_signing.sign(manifest)

    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=_seed()))
    other_public_key = export_signing.public_key_b64()
    assert export_signing.verify(manifest, signature, other_public_key) is False


def test_verify_never_raises_on_garbage_input():
    assert export_signing.verify({"a": 1}, "not-base64!!", "also-not-base64!!") is False


def test_signing_disabled_by_default(monkeypatch):
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings())
    assert export_signing.signing_enabled() is False
    assert export_signing.sign({"a": 1}) is None
    assert export_signing.public_key_b64() is None


def test_canonical_json_is_key_order_independent():
    assert export_signing.canonical_json({"b": 1, "a": 2}) == export_signing.canonical_json(
        {"a": 2, "b": 1}
    )


# ---- run_job wiring ----------------------------------------------------


async def _run_a_job(
    db_session: AsyncSession, tmp_path: Path, monkeypatch, format: str = "csv"
) -> ExportJob:
    monkeypatch.setattr(export_job_service, "_jobs_dir", lambda: tmp_path)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: db_session)
    db_session.add_all([_make_event(client_ip=f"10.0.1.{i}") for i in range(3)])
    await db_session.commit()

    job = await export_job_service.create_job(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), format, False, None, "test-admin"
    )
    await export_job_service.run_job(job.id)
    return await db_session.get(ExportJob, job.id)


async def test_run_job_builds_an_unsigned_manifest_when_signing_is_disabled(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings())
    job = await _run_a_job(db_session, tmp_path, monkeypatch)

    assert job.status == ExportJobStatus.DONE
    assert job.manifest_json is not None
    assert job.signature_b64 is None
    manifest = json.loads(job.manifest_json)
    assert manifest["job_id"] == job.id
    assert manifest["row_count"] == 3
    assert manifest["delivered_file_sha256"] == job.checksum_sha256
    # content_sha256 is the *inner* csv, not the outer zip -- must differ
    # from the delivered (zip) checksum, and must match what's actually in
    # the zip once extracted.
    assert manifest["content_sha256"] != job.checksum_sha256
    with zipfile.ZipFile(job.file_path) as zf:
        inner_bytes = zf.read(zf.namelist()[0])
    assert manifest["content_sha256"] == hashlib.sha256(inner_bytes).hexdigest()


async def test_run_job_signs_the_manifest_when_a_signing_key_is_configured(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    seed = _seed()
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=seed))
    public_key = export_signing.public_key_b64()

    job = await _run_a_job(db_session, tmp_path, monkeypatch)

    assert job.signature_b64 is not None
    manifest = json.loads(job.manifest_json)
    assert export_signing.verify(manifest, job.signature_b64, public_key) is True


async def test_run_job_xlsx_content_hash_equals_delivered_hash(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    """xlsx has no outer zip -- the delivered file *is* the content file, so
    the two hashes in the manifest must be identical."""
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings())
    job = await _run_a_job(db_session, tmp_path, monkeypatch, format="xlsx")
    manifest = json.loads(job.manifest_json)
    assert manifest["content_sha256"] == manifest["delivered_file_sha256"] == job.checksum_sha256


# ---- GET /export/jobs/{id}/manifest ------------------------------------


async def test_manifest_route_requires_admin_and_returns_signature_material(
    app_client: AsyncClient,
    admin_token,
    auth_headers,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch,
):
    seed = _seed()
    monkeypatch.setattr(export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=seed))
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
            assert status_response.json()["signed"] is True
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("export job never reached done")

    manifest_response = await app_client.get(
        f"/api/export/jobs/{job_id}/manifest", headers=auth_headers(admin_token)
    )
    assert manifest_response.status_code == 200
    body = manifest_response.json()
    assert body["algorithm"] == "ed25519"
    assert body["signature"] is not None
    assert body["public_key"] is not None
    assert export_signing.verify(body["manifest"], body["signature"], body["public_key"]) is True


async def test_manifest_route_404s_for_a_nonexistent_job(app_client: AsyncClient, admin_token, auth_headers):
    r = await app_client.get("/api/export/jobs/does-not-exist/manifest", headers=auth_headers(admin_token))
    assert r.status_code == 404
