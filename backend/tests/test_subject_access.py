"""Subject-access dossier (Faza 6.5 / docs/PRODUCT.md #4) -- one signed
document combining actor-detail activity with watchlist status."""

import base64
import secrets
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.raw_event import RawEvent
from app.models.watchlist_entry import WatchlistTargetType
from app.services import export_signing, subject_access_service, watchlist_service


def _seed() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _make_event(**overrides) -> RawEvent:
    defaults = dict(
        timestamp=datetime.now(UTC),
        duration_ms=10,
        client_ip="10.0.0.9",
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        user="alice",
        blocked=False,
    )
    defaults.update(overrides)
    return RawEvent(**defaults)


async def test_dossier_reports_not_watched_when_no_watchlist_entry(db_session: AsyncSession):
    dossier = await subject_access_service.build_dossier(db_session, "client_ip", "10.0.0.9", None)
    assert dossier.subject_type == "client_ip"
    assert dossier.watchlist.watched is False
    assert dossier.watchlist.active is None


async def test_dossier_reports_watchlist_status_when_watched(db_session: AsyncSession):
    await watchlist_service.create_entry(
        db_session,
        WatchlistTargetType.CLIENT_IP,
        "10.0.0.9",
        "flagged for review",
        "",  # any branch
        "actor-1",
    )
    dossier = await subject_access_service.build_dossier(db_session, "client_ip", "10.0.0.9", None)
    assert dossier.watchlist.watched is True
    assert dossier.watchlist.note == "flagged for review"


async def test_dossier_is_unsigned_by_default(monkeypatch, db_session: AsyncSession):
    monkeypatch.setattr(subject_access_service.export_signing, "get_settings", lambda: Settings())
    dossier = await subject_access_service.build_dossier(db_session, "user", "alice", None)
    assert dossier.signature is None
    assert dossier.public_key is None


async def test_dossier_signature_verifies_when_signing_is_configured(monkeypatch, db_session: AsyncSession):
    seed = _seed()
    monkeypatch.setattr(
        subject_access_service.export_signing, "get_settings", lambda: Settings(EXPORT_SIGNING_PRIVATE_KEY=seed)
    )
    dossier = await subject_access_service.build_dossier(db_session, "user", "alice", None)
    assert dossier.signature is not None
    manifest = subject_access_service._manifest(dossier)
    assert export_signing.verify(manifest, dossier.signature, dossier.public_key) is True


async def test_dossier_route_requires_admin(app_client: AsyncClient, viewer_token, auditor_token, auth_headers):
    for token in (viewer_token, auditor_token):
        r = await app_client.get(
            "/api/subject-access/dossier",
            params={"subject_type": "client_ip", "value": "10.0.0.9"},
            headers=auth_headers(token),
        )
        assert r.status_code == 403


async def test_dossier_route_returns_activity_and_records_audit_entry(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    db_session.add_all([_make_event(url=f"http://example.com/{i}") for i in range(3)])
    await db_session.commit()

    r = await app_client.get(
        "/api/subject-access/dossier",
        params={"subject_type": "client_ip", "value": "10.0.0.9"},
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["value"] == "10.0.0.9"
    assert body["algorithm"] == "ed25519"

    entries = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.SUBJECT_DOSSIER_EXPORTED)
        )
    ).scalars().all()
    assert len(entries) == 1
    assert "client_ip=10.0.0.9" in entries[0].detail
    assert entries[0].actor_email == "admin@example.com"


async def test_two_dossier_generations_are_both_audited_not_deduplicated(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    """Unlike the other read-access actions, generating a dossier is always
    a deliberate act -- every call gets its own entry (the timestamp in
    `detail` alone already guarantees this, but assert the behaviour)."""
    for _ in range(2):
        r = await app_client.get(
            "/api/subject-access/dossier",
            params={"subject_type": "client_ip", "value": "10.0.0.9"},
            headers=auth_headers(admin_token),
        )
        assert r.status_code == 200

    entries = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.SUBJECT_DOSSIER_EXPORTED)
        )
    ).scalars().all()
    assert len(entries) == 2
