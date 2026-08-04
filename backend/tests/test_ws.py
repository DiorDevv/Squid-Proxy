import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
