import asyncio
import logging
from datetime import UTC, datetime

import pytest

from app.services.event_store import StoredEvent
from app.services.log_parser import ParsedEvent
from app.services.ws_manager import WebSocketManager


class _FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("connection reset by peer")
        self.sent.append(payload)


def _event() -> StoredEvent:
    parsed = ParsedEvent(
        timestamp=datetime.now(UTC),
        duration_ms=1,
        client_ip="10.0.0.1",
        action="TCP_MISS",
        status_code=200,
        bytes=1,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=False,
    )
    return StoredEvent(id=1, event=parsed)


async def test_connect_accepts_and_tracks_connection():
    manager = WebSocketManager()
    ws = _FakeWebSocket()

    await manager.connect(ws)

    assert ws.accepted is True
    assert manager.connection_count == 1


async def test_disconnect_removes_connection():
    manager = WebSocketManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    manager.disconnect(ws)

    assert manager.connection_count == 0


async def test_broadcast_delivers_payload_to_connected_clients():
    manager = WebSocketManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    await manager._broadcast(_event())

    assert len(ws.sent) == 1
    assert ws.sent[0]["client_ip"] == "10.0.0.1"
    assert ws.sent[0]["domain"] == "example.com"


async def test_broadcast_drops_and_logs_dead_connections(caplog: pytest.LogCaptureFixture):
    manager = WebSocketManager()
    healthy = _FakeWebSocket()
    dead = _FakeWebSocket(fail=True)
    await manager.connect(healthy)
    await manager.connect(dead)

    with caplog.at_level(logging.WARNING):
        await manager._broadcast(_event())

    # The failing connection is dropped, the healthy one still gets the event.
    assert manager.connection_count == 1
    assert len(healthy.sent) == 1
    assert any("send failure" in record.message for record in caplog.records)


async def test_broadcast_nowait_is_a_noop_with_no_connections():
    manager = WebSocketManager()
    manager.bind_loop(asyncio.get_running_loop())

    # Must not raise even though nothing is connected.
    manager.broadcast_nowait(_event())
    await asyncio.sleep(0)


async def test_broadcast_nowait_schedules_broadcast_on_bound_loop():
    manager = WebSocketManager()
    manager.bind_loop(asyncio.get_running_loop())
    ws = _FakeWebSocket()
    await manager.connect(ws)

    manager.broadcast_nowait(_event())
    await asyncio.sleep(0)  # let the scheduled task run

    assert len(ws.sent) == 1
