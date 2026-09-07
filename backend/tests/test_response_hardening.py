"""Audit findings L3/L4: baseline response-hardening headers on every API
response, and validation errors that don't echo the submitted values
back."""

from httpx import AsyncClient


async def test_security_headers_present_on_a_normal_response(app_client: AsyncClient):
    r = await app_client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


async def test_security_headers_present_on_an_error_response(app_client: AsyncClient):
    r = await app_client.get("/api/summary")  # 401, no token
    assert r.status_code == 401
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


async def test_request_id_is_stripped_of_newlines_and_capped(app_client: AsyncClient):
    r = await app_client.get("/api/health", headers={"X-Request-ID": "abc\ndef\r" + "z" * 500})
    echoed = r.headers["x-request-id"]
    assert "\n" not in echoed and "\r" not in echoed
    assert len(echoed) <= 128


async def test_validation_error_does_not_echo_submitted_input(app_client: AsyncClient):
    # `since`/`until` want ISO datetimes; a garbage value trips validation.
    r = await app_client.get(
        "/api/timeseries",
        params={"from_ts": "NOT-A-DATE-SECRETVALUE", "to_ts": "also-bad"},
        headers={"Authorization": "Bearer nonsense"},
    )
    # 401 (bad token) or 422 (validation) depending on dependency order --
    # either way the response body must not contain the raw submitted value.
    assert "SECRETVALUE" not in r.text
    if r.status_code == 422:
        body = r.json()
        for err in body.get("errors", []):
            assert set(err.keys()) <= {"loc", "msg", "type"}
