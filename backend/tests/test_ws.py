import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


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
