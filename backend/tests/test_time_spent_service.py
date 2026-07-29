"""Tests for the session-based time-spent-per-domain estimate
(app/services/time_spent_service.py)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_category import DomainCategoryLabel
from app.models.raw_event import RawEvent
from app.services import domain_category_service
from app.services.time_spent_service import _summarize_sessions, get_time_spent, get_time_spent_by_category

GAP = timedelta(minutes=30)
BASE = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def test_summarize_sessions_empty_input_returns_zero():
    assert _summarize_sessions([], GAP) == (0, 0)


def test_summarize_sessions_single_event_has_zero_duration_one_session():
    total_seconds, session_count = _summarize_sessions([BASE], GAP)
    assert total_seconds == 0
    assert session_count == 1


def test_summarize_sessions_continuous_requests_form_one_session():
    timestamps = [BASE, BASE + timedelta(minutes=5), BASE + timedelta(minutes=10)]
    total_seconds, session_count = _summarize_sessions(timestamps, GAP)
    assert total_seconds == 600
    assert session_count == 1


def test_summarize_sessions_long_gap_splits_into_two_sessions():
    timestamps = [BASE, BASE + timedelta(minutes=5), BASE + timedelta(hours=2), BASE + timedelta(hours=2, minutes=5)]
    total_seconds, session_count = _summarize_sessions(timestamps, GAP)
    # Two 5-minute sessions, the 2-hour gap between them is not counted.
    assert total_seconds == 600
    assert session_count == 2


def _raw_event(client_ip: str, domain: str, timestamp: datetime, branch: str = "default") -> RawEvent:
    return RawEvent(
        timestamp=timestamp,
        duration_ms=1,
        client_ip=client_ip,
        branch=branch,
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url=f"http://{domain}/",
        domain=domain,
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=False,
    )


async def test_get_time_spent_groups_by_domain_and_sorts_by_duration(db_session: AsyncSession):
    db_session.add_all(
        [
            _raw_event("10.0.0.1", "long.example", BASE),
            _raw_event("10.0.0.1", "long.example", BASE + timedelta(minutes=20)),
            _raw_event("10.0.0.1", "short.example", BASE + timedelta(minutes=25)),
            # A different client's traffic must not leak into this result.
            _raw_event("10.0.0.2", "long.example", BASE + timedelta(minutes=1)),
        ]
    )
    await db_session.commit()

    items = await get_time_spent(
        db_session, "10.0.0.1", BASE - timedelta(hours=1), BASE + timedelta(hours=1)
    )

    assert [item.domain for item in items] == ["long.example", "short.example"]
    assert items[0].total_seconds == 20 * 60
    assert items[1].total_seconds == 0


async def test_get_time_spent_scopes_to_branch_when_given(db_session: AsyncSession):
    # Same client IP active on two branches (e.g. reused behind separate
    # NATs) -- without branch scoping these would incorrectly merge into one
    # inflated total for whichever branch's page an admin is viewing.
    db_session.add_all(
        [
            _raw_event("10.0.0.1", "hq.example", BASE, branch="hq"),
            _raw_event("10.0.0.1", "hq.example", BASE + timedelta(minutes=10), branch="hq"),
            _raw_event("10.0.0.1", "branch2.example", BASE, branch="branch2"),
        ]
    )
    await db_session.commit()

    hq_items = await get_time_spent(
        db_session, "10.0.0.1", BASE - timedelta(hours=1), BASE + timedelta(hours=1), branch="hq"
    )
    assert [item.domain for item in hq_items] == ["hq.example"]
    assert hq_items[0].total_seconds == 10 * 60

    branch2_items = await get_time_spent(
        db_session, "10.0.0.1", BASE - timedelta(hours=1), BASE + timedelta(hours=1), branch="branch2"
    )
    assert [item.domain for item in branch2_items] == ["branch2.example"]

    all_items = await get_time_spent(
        db_session, "10.0.0.1", BASE - timedelta(hours=1), BASE + timedelta(hours=1)
    )
    assert {item.domain for item in all_items} == {"hq.example", "branch2.example"}


async def test_get_time_spent_by_category_rolls_up_domains_sharing_a_category(db_session: AsyncSession):
    db_session.add_all(
        [
            # Both known video-streaming hostnames (category_inference.py) --
            # their per-domain totals must combine into one video_streaming row.
            _raw_event("10.0.0.3", "youtube.com", BASE),
            _raw_event("10.0.0.3", "youtube.com", BASE + timedelta(minutes=10)),
            _raw_event("10.0.0.3", "netflix.com", BASE + timedelta(minutes=15)),
            _raw_event("10.0.0.3", "netflix.com", BASE + timedelta(minutes=25)),
            # Unrelated domain, unrelated category.
            _raw_event("10.0.0.3", "github.com", BASE + timedelta(minutes=30)),
        ]
    )
    await db_session.commit()

    items = {
        item.category: item
        for item in await get_time_spent_by_category(
            db_session, "10.0.0.3", BASE - timedelta(hours=1), BASE + timedelta(hours=1)
        )
    }

    assert DomainCategoryLabel.VIDEO_STREAMING in items
    # youtube.com session (0-10m = 600s) + netflix.com session (15-25m = 600s)
    assert items[DomainCategoryLabel.VIDEO_STREAMING].total_seconds == 1200
    assert items[DomainCategoryLabel.VIDEO_STREAMING].session_count == 2
    assert DomainCategoryLabel.WORK_TOOLS in items


async def test_get_time_spent_by_category_respects_admin_override(db_session: AsyncSession):
    db_session.add_all(
        [
            _raw_event("10.0.0.4", "youtube.com", BASE),
            _raw_event("10.0.0.4", "youtube.com", BASE + timedelta(minutes=10)),
        ]
    )
    await domain_category_service.set_category(db_session, "youtube.com", DomainCategoryLabel.WORK_TOOLS)
    await db_session.commit()

    items = {
        item.category: item
        for item in await get_time_spent_by_category(
            db_session, "10.0.0.4", BASE - timedelta(hours=1), BASE + timedelta(hours=1)
        )
    }

    assert DomainCategoryLabel.WORK_TOOLS in items
    assert DomainCategoryLabel.VIDEO_STREAMING not in items
