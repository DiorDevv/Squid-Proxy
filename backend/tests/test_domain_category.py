"""Tests for domain category assignment (app/services/domain_category_service.py)
and the by-category usage rollup (app/services/stats_service.get_usage_by_category)
-- the latter is a regression test for a real bug: SQLAlchemy's Enum type
persists/reads a Python enum's *name* ("UNCATEGORIZED"), not its `.value`
("uncategorized"), so the coalesce fallback for domains with no assigned
category must match that or every query raises a LookupError."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.services import domain_category_service
from app.services.stats_service import get_usage_by_category


async def test_set_category_creates_then_updates(db_session: AsyncSession):
    created = await domain_category_service.set_category(
        db_session, "example.com", DomainCategoryLabel.SOCIAL_MEDIA, "actor-1"
    )
    assert created.category == DomainCategoryLabel.SOCIAL_MEDIA

    updated = await domain_category_service.set_category(
        db_session, "example.com", DomainCategoryLabel.WORK_TOOLS, "actor-1"
    )
    assert updated.category == DomainCategoryLabel.WORK_TOOLS

    all_rows = await domain_category_service.list_all(db_session)
    assert len(all_rows) == 1
    assert all_rows[0].category == DomainCategoryLabel.WORK_TOOLS


async def test_set_category_records_audit_entry(db_session: AsyncSession):
    await domain_category_service.set_category(
        db_session, "gambling-site.example", DomainCategoryLabel.GAMBLING, "actor-1"
    )

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DOMAIN_CATEGORY_SET)
        )
    ).scalar_one()
    assert entry.actor_user_id == "actor-1"
    assert "gambling-site.example" in entry.detail
    assert "gambling" in entry.detail


async def test_usage_by_category_groups_uncategorized_domains_without_error(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="no-category.com", request_count=10, blocked_count=0, total_bytes=100
            ),
        ]
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = await get_usage_by_category(db_session, since, until)

    assert len(items) == 1
    assert items[0].category == DomainCategoryLabel.UNCATEGORIZED
    assert items[0].request_count == 10
    assert items[0].total_bytes == 100


async def test_usage_by_category_splits_categorized_and_uncategorized(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="social.example", request_count=5, blocked_count=0, total_bytes=50
            ),
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="mystery.example", request_count=3, blocked_count=0, total_bytes=30
            ),
        ]
    )
    await domain_category_service.set_category(
        db_session, "social.example", DomainCategoryLabel.SOCIAL_MEDIA, "actor-1"
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert items[DomainCategoryLabel.SOCIAL_MEDIA].request_count == 5
    assert items[DomainCategoryLabel.UNCATEGORIZED].request_count == 3


async def test_usage_by_category_falls_back_to_inferred_category(db_session: AsyncSession):
    """A domain nobody has explicitly categorized still lands somewhere
    useful (not a flat "uncategorized" bucket) via category_inference.py --
    e.g. a known video site's traffic shows up under video_streaming with
    zero admin effort."""
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="youtube.com", request_count=7, blocked_count=0, total_bytes=700
            ),
        ]
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert DomainCategoryLabel.VIDEO_STREAMING in items
    assert items[DomainCategoryLabel.VIDEO_STREAMING].request_count == 7


async def test_usage_by_category_admin_override_wins_over_inference(db_session: AsyncSession):
    """youtube.com would infer as video_streaming -- an explicit admin
    override must still take precedence."""
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="youtube.com", request_count=4, blocked_count=0, total_bytes=400
            ),
        ]
    )
    await domain_category_service.set_category(
        db_session, "youtube.com", DomainCategoryLabel.WORK_TOOLS, "actor-1"
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert DomainCategoryLabel.WORK_TOOLS in items
    assert DomainCategoryLabel.VIDEO_STREAMING not in items


async def test_export_to_csv_round_trips_through_import(db_session: AsyncSession):
    await domain_category_service.set_category(
        db_session, "social.example", DomainCategoryLabel.SOCIAL_MEDIA, "actor-1"
    )
    await domain_category_service.set_category(
        db_session, "shop.example", DomainCategoryLabel.SHOPPING, "actor-1"
    )

    rows = await domain_category_service.list_all(db_session)
    csv_text = domain_category_service.export_to_csv(rows)
    assert csv_text.splitlines()[0] == "domain,category"

    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-2")
    assert applied == 2
    assert errors == []


async def test_import_from_csv_creates_new_and_updates_existing(db_session: AsyncSession):
    await domain_category_service.set_category(
        db_session, "already-tagged.example", DomainCategoryLabel.NEWS, "actor-1"
    )

    csv_text = "domain,category\nalready-tagged.example,work_tools\nbrand-new.example,gaming\n"
    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-2")

    assert applied == 2
    assert errors == []
    rows = {row.domain: row.category for row in await domain_category_service.list_all(db_session)}
    assert rows["already-tagged.example"] == DomainCategoryLabel.WORK_TOOLS
    assert rows["brand-new.example"] == DomainCategoryLabel.GAMING


async def test_import_from_csv_reports_bad_rows_without_aborting_the_good_ones(db_session: AsyncSession):
    csv_text = (
        "domain,category\n"
        "good.example,shopping\n"
        ",gaming\n"  # missing domain
        "bad-category.example,not_a_real_category\n"
        "also-good.example,news\n"
    )
    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-1")

    assert applied == 2
    assert len(errors) == 2
    rows = {row.domain: row.category for row in await domain_category_service.list_all(db_session)}
    assert rows["good.example"] == DomainCategoryLabel.SHOPPING
    assert rows["also-good.example"] == DomainCategoryLabel.NEWS
    assert "bad-category.example" not in rows


async def test_import_from_csv_rejects_missing_header(db_session: AsyncSession):
    applied, errors = await domain_category_service.import_from_csv(
        db_session, "not,the,right,header\nfoo,bar,baz,qux\n", "actor-1"
    )
    assert applied == 0
    assert len(errors) == 1
    assert "header" in errors[0][2].lower()


async def test_domain_categories_export_route_returns_csv(
    app_client: AsyncClient, admin_token, auth_headers
):
    await app_client.put(
        "/api/domain-categories/export-test.example",
        headers=auth_headers(admin_token),
        json={"category": "gaming"},
    )

    response = await app_client.get("/api/domain-categories/export", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "export-test.example,gaming" in response.text


async def test_domain_categories_import_route_applies_rows(
    app_client: AsyncClient, admin_token, auth_headers
):
    csv_bytes = b"domain,category\nimported.example,music_streaming\n"
    response = await app_client.post(
        "/api/domain-categories/import",
        headers=auth_headers(admin_token),
        files={"file": ("domains.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] == 1
    assert body["errors"] == []

    list_response = await app_client.get("/api/domain-categories", headers=auth_headers(admin_token))
    domains = {row["domain"]: row["category"] for row in list_response.json()}
    assert domains["imported.example"] == "music_streaming"


async def test_domain_categories_import_route_requires_admin(
    app_client: AsyncClient, viewer_token, auth_headers
):
    csv_bytes = b"domain,category\nx.example,news\n"
    response = await app_client.post(
        "/api/domain-categories/import",
        headers=auth_headers(viewer_token),
        files={"file": ("domains.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 403


async def test_domain_categories_route_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/domain-categories", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_import_from_csv_records_one_audit_entry_not_one_per_row(db_session: AsyncSession):
    """Regression test for the bulk-import performance fix: import used to
    call set_category() per row, which recorded one DOMAIN_CATEGORY_SET
    audit entry per row. A bulk import should record exactly one summary
    DOMAIN_CATEGORY_IMPORTED entry instead."""
    csv_text = "domain,category\na.example,news\nb.example,gaming\nc.example,shopping\n"
    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-1")
    assert applied == 3
    assert errors == []

    entries = (
        (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DOMAIN_CATEGORY_IMPORTED)))
        .scalars()
        .all()
    )
    assert len(entries) == 1
    assert entries[0].actor_user_id == "actor-1"
    assert "3 domain(s)" in entries[0].detail
    assert "a.example" in entries[0].detail

    set_entries = (
        (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DOMAIN_CATEGORY_SET)))
        .scalars()
        .all()
    )
    assert set_entries == []


async def test_import_from_csv_duplicate_domain_last_row_wins(db_session: AsyncSession):
    csv_text = "domain,category\ndupe.example,news\ndupe.example,gaming\n"
    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-1")
    assert applied == 2
    assert errors == []

    rows = {row.domain: row.category for row in await domain_category_service.list_all(db_session)}
    assert rows["dupe.example"] == DomainCategoryLabel.GAMING


async def test_import_from_csv_does_not_record_audit_entry_when_nothing_applied(db_session: AsyncSession):
    applied, errors = await domain_category_service.import_from_csv(
        db_session, "domain,category\n,gaming\n", "actor-1"
    )
    assert applied == 0
    assert len(errors) == 1

    entries = (
        (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DOMAIN_CATEGORY_IMPORTED)))
        .scalars()
        .all()
    )
    assert entries == []


async def test_export_to_csv_escapes_leading_formula_characters(db_session: AsyncSession):
    """A domain isn't validated as a real hostname (PUT /{domain} accepts
    any string) -- if one starts with a spreadsheet formula trigger
    character, the exported CSV cell must not execute as a formula when
    opened directly in Excel/Sheets. Round-tripping the export back through
    import must still recover the exact original domain."""
    await domain_category_service.set_category(
        db_session, "=cmd|'/c calc'!a1", DomainCategoryLabel.OTHER, "actor-1"
    )

    rows = await domain_category_service.list_all(db_session)
    csv_text = domain_category_service.export_to_csv(rows)
    data_line = csv_text.splitlines()[1]
    assert data_line.startswith("'=cmd")

    applied, errors = await domain_category_service.import_from_csv(db_session, csv_text, "actor-2")
    assert applied == 1
    assert errors == []
    imported = {row.domain: row.category for row in await domain_category_service.list_all(db_session)}
    assert "=cmd|'/c calc'!a1" in imported


async def test_set_and_list_domain_category_via_api(app_client: AsyncClient, admin_token, auth_headers):
    put_response = await app_client.put(
        "/api/domain-categories/video.example",
        headers=auth_headers(admin_token),
        json={"category": "video_streaming"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["category"] == "video_streaming"

    list_response = await app_client.get("/api/domain-categories", headers=auth_headers(admin_token))
    assert list_response.status_code == 200
    domains = {row["domain"]: row["category"] for row in list_response.json()}
    assert domains["video.example"] == "video_streaming"
