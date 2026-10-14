"""Multi-branch scopes, feature permissions and access end dates
(core/branch_scope.py, core/permissions.py, api/deps.py, user_service.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import branch_scope
from app.core.config import LogSource, Settings
from app.core.security import hash_password
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.raw_event import RawEvent
from app.models.user import User, UserRole

PASSWORD = "access-pass-123"
THREE_BRANCHES = Settings(
    LOG_SOURCES=[
        LogSource(branch="hq", path="/data/hq/access.log"),
        LogSource(branch="west", path="/data/west/access.log"),
        LogSource(branch="east", path="/data/east/access.log"),
    ]
)


@pytest.fixture
def three_branches(monkeypatch):
    import app.api.routes.branches as branches_module
    import app.services.user_service as user_service_module

    monkeypatch.setattr(branches_module, "get_settings", lambda: THREE_BRANCHES)
    monkeypatch.setattr(user_service_module, "get_settings", lambda: THREE_BRANCHES)


async def _login_new_user(
    app_client: AsyncClient, db_session: AsyncSession, username: str, **fields
) -> str:
    fields.setdefault("role", UserRole.VIEWER)
    db_session.add(User(username=username, hashed_password=hash_password(PASSWORD), **fields))
    await db_session.commit()
    response = await app_client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _event(branch: str, client_ip: str) -> RawEvent:
    return RawEvent(
        timestamp=datetime.now(UTC) - timedelta(minutes=1),
        duration_ms=1,
        client_ip=client_ip,
        branch=branch,
        action="TCP_MISS",
        status_code=200,
        bytes=10,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        blocked=False,
    )


# ---- core/branch_scope ------------------------------------------------------


def test_normalize_branches_sorts_dedupes_and_treats_empty_as_unrestricted():
    assert branch_scope.normalize_branches(["west", "hq", "west", " "]) == ("hq", "west")
    assert branch_scope.normalize_branches([]) is None
    assert branch_scope.normalize_branches(None) is None


def test_scope_tag_round_trips_and_keeps_single_branch_tags_plain():
    assert branch_scope.scope_tag("hq") == "hq"
    assert branch_scope.parse_scope_tag("hq") == "hq"
    assert branch_scope.scope_tag(("hq", "west")) == "hq,west"
    assert branch_scope.parse_scope_tag("west,hq") == ("hq", "west")
    assert branch_scope.parse_scope_tag(None) is None


def test_scope_within():
    assert branch_scope.scope_within("hq", ("hq", "west"))
    assert branch_scope.scope_within(("hq", "west"), ("hq", "west"))
    assert not branch_scope.scope_within(("hq", "east"), ("hq", "west"))
    assert not branch_scope.scope_within(None, ("hq",))
    assert branch_scope.scope_within(None, None)


def test_branch_filter_uses_in_for_several_branches():
    single = str(branch_scope.branch_filter(RawEvent.branch, "hq").compile())
    several = str(branch_scope.branch_filter(RawEvent.branch, ("hq", "west")).compile())
    assert "=" in single and "IN" not in single
    assert "IN" in several


def test_user_branch_shorthand_sets_a_one_element_list():
    user = User(username="x", hashed_password="x", role=UserRole.VIEWER, branch="hq")
    assert user.branches == ["hq"]
    user.branches = ["west", "hq"]
    # Never None for a limited account -- comparisons against it fail closed.
    assert user.branch == "hq,west"


# ---- data routes ------------------------------------------------------------


async def test_multi_branch_user_sees_only_their_branches_combined(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    db_session.add_all([_event("hq", "10.0.0.1"), _event("west", "10.0.0.2"), _event("east", "10.0.0.3")])
    await db_session.commit()
    token = await _login_new_user(app_client, db_session, "two-branches", branches=["hq", "west"])

    response = await app_client.get("/api/events?range=1h", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    assert sorted(item["branch"] for item in response.json()["items"]) == ["hq", "west"]

    one = await app_client.get("/api/events?range=1h&branch=west", headers=auth_headers(token))
    assert [item["client_ip"] for item in one.json()["items"]] == ["10.0.0.2"]

    other = await app_client.get("/api/events?range=1h&branch=east", headers=auth_headers(token))
    assert other.status_code == 403


async def test_branches_route_lists_only_the_users_branches(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers, three_branches
):
    token = await _login_new_user(app_client, db_session, "two-branches", branches=["west", "hq"])
    response = await app_client.get("/api/branches", headers=auth_headers(token))
    assert [item["slug"] for item in response.json()["items"]] == ["hq", "west"]


async def test_login_and_me_report_branches_and_permissions(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _login_new_user(
        app_client, db_session, "me-check", branches=["hq", "west"], permissions=["export"]
    )
    me = (await app_client.get("/api/auth/me", headers=auth_headers(token))).json()
    assert me["branches"] == ["hq", "west"]
    assert me["permissions"] == ["export"]


# ---- user management: branches ---------------------------------------------


async def test_create_user_with_several_branches(
    app_client: AsyncClient, admin_token, auth_headers, three_branches
):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "watcher", "role": "viewer", "branches": ["west", "hq"]},
    )
    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert user["branches"] == ["hq", "west"]
    assert user["branch"] == "hq,west"


async def test_create_user_rejects_an_unknown_branch_in_the_list(
    app_client: AsyncClient, admin_token, auth_headers, three_branches
):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "watcher", "role": "viewer", "branches": ["hq", "nowhere"]},
    )
    assert response.status_code == 400


async def test_update_branches_route(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession, three_branches
):
    created = await app_client.post(
        "/api/users", headers=auth_headers(admin_token), json={"username": "mover", "role": "viewer"}
    )
    user_id = created.json()["user"]["id"]

    response = await app_client.patch(
        f"/api/users/{user_id}/branch",
        headers=auth_headers(admin_token),
        json={"branches": ["east", "hq"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["branches"] == ["east", "hq"]

    cleared = await app_client.patch(
        f"/api/users/{user_id}/branch", headers=auth_headers(admin_token), json={"branches": []}
    )
    assert cleared.json()["branches"] is None


async def test_branch_limited_admin_cannot_grant_outside_their_branches(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers, three_branches
):
    token = await _login_new_user(
        app_client, db_session, "two-branch-admin", role=UserRole.ADMIN, branches=["hq", "west"]
    )
    outside = await app_client.post(
        "/api/users",
        headers=auth_headers(token),
        json={"username": "viewer-v1", "role": "viewer", "branches": ["hq", "east"]},
    )
    assert outside.status_code == 403

    # Asking for "every branch" gets the admin's own branches, never more.
    defaulted = await app_client.post(
        "/api/users", headers=auth_headers(token), json={"username": "viewer-v2", "role": "viewer"}
    )
    assert defaulted.status_code == 201, defaulted.text
    assert defaulted.json()["user"]["branches"] == ["hq", "west"]

    listed = await app_client.get("/api/users", headers=auth_headers(token))
    assert {u["username"] for u in listed.json()} == {"two-branch-admin", "viewer-v2"}


# ---- permissions ------------------------------------------------------------


async def test_viewer_gets_watchlist_only_once_granted(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    token = await _login_new_user(app_client, db_session, "plain-viewer")
    assert (await app_client.get("/api/watchlist", headers=auth_headers(token))).status_code == 403

    user_id = (await db_session.execute(select(User.id).where(User.username == "plain-viewer"))).scalar_one()
    granted = await app_client.patch(
        f"/api/users/{user_id}/permissions",
        headers=auth_headers(admin_token),
        json={"permissions": ["watchlist"]},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["effective_permissions"] == ["watchlist"]

    # The permission change bumped token_version -- sign in again.
    relogin = await app_client.post(
        "/api/auth/login", json={"username": "plain-viewer", "password": PASSWORD}
    )
    token = relogin.json()["access_token"]
    assert (await app_client.get("/api/watchlist", headers=auth_headers(token))).status_code == 200


async def test_admin_without_a_permission_loses_that_feature(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _login_new_user(
        app_client, db_session, "narrow-admin", role=UserRole.ADMIN, permissions=["watchlist"]
    )
    assert (await app_client.get("/api/watchlist", headers=auth_headers(token))).status_code == 200
    assert (await app_client.get("/api/alert-settings", headers=auth_headers(token))).status_code == 403
    # User management stays role-based.
    assert (await app_client.get("/api/users", headers=auth_headers(token))).status_code == 200


async def test_admin_cannot_grant_a_permission_they_lack(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _login_new_user(
        app_client, db_session, "narrow-admin", role=UserRole.ADMIN, permissions=["watchlist"]
    )
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(token),
        json={"username": "viewer-v3", "role": "viewer", "permissions": ["watchlist", "raw_export"]},
    )
    assert response.status_code == 403
    assert "raw_export" in response.json()["detail"]


async def test_unknown_permission_is_rejected(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "viewer-v4", "role": "viewer", "permissions": ["fly"]},
    )
    assert response.status_code == 400


async def test_auditor_defaults_allow_list_exports_but_not_raw_exports(
    app_client: AsyncClient, auditor_token, auth_headers
):
    who = await app_client.get("/api/analytics/actors/export?range=1h", headers=auth_headers(auditor_token))
    assert who.status_code == 200
    raw = await app_client.get("/api/export?range=1h", headers=auth_headers(auditor_token))
    assert raw.status_code == 403


# ---- access end date --------------------------------------------------------


async def test_expired_account_cannot_sign_in(app_client: AsyncClient, db_session: AsyncSession):
    db_session.add(
        User(
            username="expired",
            hashed_password=hash_password(PASSWORD),
            role=UserRole.VIEWER,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db_session.commit()
    response = await app_client.post("/api/auth/login", json={"username": "expired", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["detail"] == "account_expired"


async def test_live_session_ends_when_the_end_date_passes(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    token = await _login_new_user(app_client, db_session, "temp-viewer")
    assert (await app_client.get("/api/branches", headers=auth_headers(token))).status_code == 200

    user_id = (await db_session.execute(select(User.id).where(User.username == "temp-viewer"))).scalar_one()
    past = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    response = await app_client.patch(
        f"/api/users/{user_id}/expiry", headers=auth_headers(admin_token), json={"expires_at": past}
    )
    assert response.status_code == 200, response.text

    assert (await app_client.get("/api/branches", headers=auth_headers(token))).status_code == 401


async def test_super_admin_cannot_get_an_end_date(app_client: AsyncClient, admin_token, auth_headers):
    future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "sa2", "role": "superadmin", "expires_at": future},
    )
    assert response.status_code == 400


# ---- export jobs ------------------------------------------------------------


async def test_export_jobs_visible_by_scope(db_session: AsyncSession):
    from app.services import export_job_service

    now = datetime.now(UTC)
    for tag in ("hq", "east", "hq,west", None):
        db_session.add(
            ExportJob(
                id=f"job-{tag}",
                status=ExportJobStatus.DONE,
                format="csv",
                since=now - timedelta(hours=1),
                until=now,
                blocked_only=False,
                branch=tag,
                created_at=now,
            )
        )
    await db_session.commit()

    visible = await export_job_service.list_jobs(db_session, branch=("hq", "west"))
    assert sorted(job.branch for job in visible) == ["hq", "hq,west"]
