"""Tests for GET /api/branches (app/api/routes/branches.py)."""

from httpx import AsyncClient

from app.core.config import LogSource, Settings


async def test_branches_route_returns_default_branch_with_no_log_sources_configured(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    import app.api.routes.branches as branches_module

    monkeypatch.setattr(branches_module, "get_settings", lambda: Settings())

    response = await app_client.get("/api/branches", headers=auth_headers(admin_token))
    assert response.status_code == 200
    items = response.json()["items"]
    assert items == [{"slug": "default", "label": "Default"}]


async def test_branches_route_lists_every_configured_log_source(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    import app.api.routes.branches as branches_module

    monkeypatch.setattr(
        branches_module,
        "get_settings",
        lambda: Settings(
            LOG_SOURCES=[
                LogSource(branch="hq", path="/data/hq/access.log"),
                LogSource(branch="branch-office", path="/data/branch-office/access.log"),
            ]
        ),
    )

    response = await app_client.get("/api/branches", headers=auth_headers(admin_token))
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["slug"] for item in items} == {"hq", "branch-office"}
    assert {item["label"] for item in items} == {"Hq", "Branch Office"}
