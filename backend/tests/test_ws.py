import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

import app.api.routes.ws as ws_module
from app.models.user import User
from tests.test_branch_scoping import _scoped_viewer_token


async def test_ws_connection_rejected_without_ticket(test_app):
    with TestClient(test_app) as client, pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/live"):
        pass


async def test_ws_connection_rejected_with_invalid_ticket(test_app):
    with (
        TestClient(test_app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/live?ticket=not-a-real-ticket"),
    ):
        pass


async def test_ws_connection_accepted_with_valid_ticket(test_app, admin_token):
    with TestClient(test_app) as client:
        ticket_response = client.post(
            "/api/auth/ws-ticket", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}") as websocket:
            assert websocket is not None


async def test_ws_ticket_is_single_use(test_app, admin_token):
    with TestClient(test_app) as client:
        ticket_response = client.post(
            "/api/auth/ws-ticket", headers={"Authorization": f"Bearer {admin_token}"}
        )
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}"):
            pass

        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(f"/ws/live?ticket={ticket}"),
        ):
            pass


async def test_ws_connect_threads_the_users_branch_onto_the_connection(
    test_app, app_client, db_session
):
    """Proves the new wiring end to end: User.branch -> access token claim
    -> issue_ws_ticket -> WsTicketStore -> ws.py -> ws_manager.connect --
    the actual per-connection filtering behavior once that branch lands in
    the manager is covered exhaustively at the unit level in
    test_ws_manager.py; this only needs to prove the branch actually gets
    there for a real login."""
    token = await _scoped_viewer_token(app_client, db_session, branch="default")

    with TestClient(test_app) as client:
        ticket_response = client.post(
            "/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}
        )
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}"):
            connections = test_app.state.ws_manager._connections
            assert len(connections) == 1
            assert list(connections.values()) == ["default"]


async def test_ws_connect_leaves_an_unrestricted_users_connection_unscoped(
    test_app, admin_token
):
    with TestClient(test_app) as client:
        ticket_response = client.post(
            "/api/auth/ws-ticket", headers={"Authorization": f"Bearer {admin_token}"}
        )
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}"):
            connections = test_app.state.ws_manager._connections
            assert len(connections) == 1
            assert list(connections.values()) == [None]


# --- Periodic re-authorization: the ticket is only ever checked once, at
# handshake, so without this an already-open connection would keep
# streaming a since-changed/revoked branch scope for as long as the socket
# stays open. ---


async def test_ws_connection_closed_when_branch_changes_mid_session(
    test_app, app_client, db_session, monkeypatch
):
    monkeypatch.setattr(ws_module, "REAUTH_INTERVAL_SECONDS", 0.05)
    token = await _scoped_viewer_token(app_client, db_session, branch="default")

    with TestClient(test_app) as client:
        ticket_response = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}") as websocket:
            user = (
                await db_session.execute(select(User).where(User.email == "scoped@example.com"))
            ).scalar_one()
            user.branch = "branch-b"
            await db_session.commit()

            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()
            assert exc_info.value.code == 1008


async def test_ws_connection_closed_when_user_deleted_mid_session(test_app, app_client, db_session, monkeypatch):
    monkeypatch.setattr(ws_module, "REAUTH_INTERVAL_SECONDS", 0.05)
    token = await _scoped_viewer_token(app_client, db_session, branch="default")

    with TestClient(test_app) as client:
        ticket_response = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}") as websocket:
            user = (
                await db_session.execute(select(User).where(User.email == "scoped@example.com"))
            ).scalar_one()
            await db_session.delete(user)
            await db_session.commit()

            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()
            assert exc_info.value.code == 1008


async def test_ws_connection_survives_reauth_when_nothing_changed(test_app, app_client, db_session, monkeypatch):
    """The periodic check itself must not be the thing that disconnects a
    still-valid session."""
    monkeypatch.setattr(ws_module, "REAUTH_INTERVAL_SECONDS", 0.05)
    token = await _scoped_viewer_token(app_client, db_session, branch="default")

    with TestClient(test_app) as client:
        ticket_response = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})
        ticket = ticket_response.json()["ticket"]

        with client.websocket_connect(f"/ws/live?ticket={ticket}") as websocket:
            import time

            time.sleep(0.2)  # several re-auth cycles' worth
            assert websocket is not None
            assert len(test_app.state.ws_manager._connections) == 1
