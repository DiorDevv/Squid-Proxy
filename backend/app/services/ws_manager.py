"""Tracks connected /ws/live clients and broadcasts new events to them.

Events are coalesced into arrays and sent at most every BATCH_WINDOW_SECONDS
(or immediately once MAX_BATCH_SIZE accumulates) rather than one asyncio
task + one `send_json` per event. At demo-scale traffic this didn't matter,
but it doesn't hold up once either event throughput or connected-viewer
count grows: N events x M viewers otherwise means N*M scheduled sends per
broadcast window, with zero batching.
"""

import asyncio
import logging

from fastapi import WebSocket

from app.schemas.events import EventDetail
from app.services.event_store import StoredEvent

logger = logging.getLogger(__name__)


class WebSocketManager:
    BATCH_WINDOW_SECONDS = 0.2
    MAX_BATCH_SIZE = 200
    # A stalled peer (backgrounded mobile browser, dead TCP connection the
    # OS hasn't reaped yet) would otherwise hang send_json() indefinitely,
    # delaying delivery to every other connection queued behind it in the
    # same flush pass -- bound it and treat a timeout the same as any other
    # send failure: drop that connection, keep going for the rest.
    SEND_TIMEOUT_SECONDS = 5.0

    def __init__(self) -> None:
        # None = unrestricted (receives every branch's events) -- matches
        # every existing caller's default, so a connection whose branch is
        # never specified behaves exactly as before this per-connection
        # filtering existed.
        self._connections: dict[WebSocket, str | None] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: list[dict] = []
        self._flush_scheduled = False

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket, branch: str | None = None) -> None:
        await websocket.accept()
        self._connections[websocket] = branch
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def broadcast_nowait(self, stored: StoredEvent) -> None:
        """Buffer `stored` for the next batched send. Called from the log
        tailer's synchronous per-line callback, so this must never block or
        await -- it only appends to a list and, at most, schedules a task."""
        if not self._connections or self._loop is None:
            return
        self._pending.append(self._serialize(stored))
        if len(self._pending) >= self.MAX_BATCH_SIZE:
            self._loop.create_task(self._flush_pending())
            return
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self._loop.create_task(self._flush_after_delay())

    @staticmethod
    def _serialize(stored: StoredEvent) -> dict:
        return EventDetail.from_parsed(stored.id, stored.event).model_dump(mode="json")

    async def _flush_after_delay(self) -> None:
        await asyncio.sleep(self.BATCH_WINDOW_SECONDS)
        await self._flush_pending()

    async def _flush_pending(self) -> None:
        # Reset here (not just at the call sites) so it's correct regardless
        # of whether this run was triggered by the delay timer or by hitting
        # MAX_BATCH_SIZE -- either way, the next event should be free to
        # schedule a fresh flush.
        self._flush_scheduled = False
        if not self._pending:
            return
        batch, self._pending = self._pending, []

        dead: list[WebSocket] = []
        for connection, conn_branch in list(self._connections.items()):
            # None = unrestricted, sees every branch's events unfiltered --
            # otherwise only forward the slice of this batch matching the
            # connection's own branch (see WsTicketStore/ws.py for how that
            # branch got attached to the connection in the first place).
            filtered = (
                batch
                if conn_branch is None
                else [item for item in batch if item.get("branch") == conn_branch]
            )
            if not filtered:
                # Nothing in this batch belongs to this connection's branch
                # -- skip the send entirely rather than pushing a pointless
                # empty-array frame every batch tick.
                continue
            try:
                await asyncio.wait_for(connection.send_json(filtered), timeout=self.SEND_TIMEOUT_SECONDS)
            except Exception:
                logger.warning("Dropping /ws/live connection after send failure", exc_info=True)
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)
