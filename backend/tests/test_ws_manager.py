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
        self.sent: list[list[dict]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: list[dict]) -> None:
        if self.fail:
            raise RuntimeError("connection reset by peer")
        self.sent.append(payload)


def _event(client_ip: str = "10.0.0.1") -> StoredEvent:
    parsed = ParsedEvent(
        timestamp=datetime.now(UTC),
        duration_ms=1,
        client_ip=client_ip,
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


async def test_flush_pending_delivers_batch_to_connected_clients():
    manager = WebSocketManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    manager._pending.append(manager._serialize(_event()))
    await manager._flush_pending()

    assert len(ws.sent) == 1
    batch = ws.sent[0]
    assert len(batch) == 1
    assert batch[0]["client_ip"] == "10.0.0.1"
    assert batch[0]["domain"] == "example.com"


async def test_flush_pending_with_nothing_pending_is_a_noop():
    manager = WebSocketManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    await manager._flush_pending()

    assert ws.sent == []


async def test_flush_pending_drops_and_logs_dead_connections(caplog: pytest.LogCaptureFixture):
    manager = WebSocketManager()
    healthy = _FakeWebSocket()
    dead = _FakeWebSocket(fail=True)
    await manager.connect(healthy)
    await manager.connect(dead)

    manager._pending.append(manager._serialize(_event()))
    with caplog.at_level(logging.WARNING):
        await manager._flush_pending()

    # The failing connection is dropped, the healthy one still gets the batch.
    assert manager.connection_count == 1
    assert len(healthy.sent) == 1
    assert any("send failure" in record.message for record in caplog.records)


async def test_broadcast_nowait_is_a_noop_with_no_connections():
    manager = WebSocketManager()
    manager.bind_loop(asyncio.get_running_loop())

    # Must not raise even though nothing is connected.
    manager.broadcast_nowait(_event())
    await asyncio.sleep(0)


async def test_broadcast_nowait_delivers_after_the_batch_window():
    manager = WebSocketManager()
    manager.BATCH_WINDOW_SECONDS = 0  # no need to actually wait in a test
    manager.bind_loop(asyncio.get_running_loop())
    ws = _FakeWebSocket()
    await manager.connect(ws)

    manager.broadcast_nowait(_event())
    # A bare `await asyncio.sleep(0)` only yields once, which isn't enough
    # hops to run the scheduled task through its own internal awaits (the
    # delay sleep, then the send) to completion -- a tiny real sleep is
    # simpler than juggling exact yield counts.
    await asyncio.sleep(0.01)

    assert len(ws.sent) == 1
    assert len(ws.sent[0]) == 1


async def test_broadcast_nowait_coalesces_several_events_into_one_send():
    """The whole point of batching: events queued within the same window
    arrive as one array, not one send() per event."""
    manager = WebSocketManager()
    manager.BATCH_WINDOW_SECONDS = 0
    manager.bind_loop(asyncio.get_running_loop())
    ws = _FakeWebSocket()
    await manager.connect(ws)

    manager.broadcast_nowait(_event("10.0.0.1"))
    manager.broadcast_nowait(_event("10.0.0.2"))
    manager.broadcast_nowait(_event("10.0.0.3"))
    await asyncio.sleep(0.01)

    assert len(ws.sent) == 1
    batch = ws.sent[0]
    assert [item["client_ip"] for item in batch] == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]


async def test_broadcast_nowait_flushes_immediately_at_max_batch_size():
    manager = WebSocketManager()
    manager.MAX_BATCH_SIZE = 3
    # Not what this test is exercising, but the first append below still
    # schedules a delayed flush before the third one short-circuits it --
    # left at the real default, that stray task would still be sleeping
    # (unawaited) when the test function returns.
    manager.BATCH_WINDOW_SECONDS = 0
    manager.bind_loop(asyncio.get_running_loop())
    ws = _FakeWebSocket()
    await manager.connect(ws)

    # None of these should have to wait for BATCH_WINDOW_SECONDS -- hitting
    # MAX_BATCH_SIZE flushes right away.
    manager.broadcast_nowait(_event("10.0.0.1"))
    manager.broadcast_nowait(_event("10.0.0.2"))
    manager.broadcast_nowait(_event("10.0.0.3"))
    await asyncio.sleep(0.01)

    assert len(ws.sent) == 1
    assert len(ws.sent[0]) == 3
