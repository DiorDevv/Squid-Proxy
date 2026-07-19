"""Tracks connected /ws/live clients and broadcasts new events to them."""

import asyncio
import logging

from fastapi import WebSocket

from app.services.event_store import StoredEvent

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def broadcast_nowait(self, stored: StoredEvent) -> None:
        """Schedule a broadcast from a synchronous context (the tailer's callback)."""
        if not self._connections or self._loop is None:
            return
        self._loop.create_task(self._broadcast(stored))

    async def _broadcast(self, stored: StoredEvent) -> None:
        payload = {
            "id": stored.id,
            "timestamp": stored.event.timestamp.isoformat(),
            "client_ip": stored.event.client_ip,
            "action": stored.event.action,
            "status_code": stored.event.status_code,
            "method": stored.event.method,
            "domain": stored.event.domain,
            "url": stored.event.url,
            "user": stored.event.user,
            "bytes": stored.event.bytes,
            "blocked": stored.event.blocked,
        }
        dead: list[WebSocket] = []
        for connection in list(self._connections):
            try:
                await connection.send_json(payload)
            except Exception:
                logger.warning("Dropping /ws/live connection after send failure", exc_info=True)
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)
