import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, status

from app.models import db as db_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# How often an already-open connection's branch scope is re-checked against
# the live User row -- the ticket itself (see WsTicketStore) is only ever
# checked once, at handshake, so without this a connection opened before an
# admin narrows or reassigns that user's branch would keep streaming the
# old (broader) scope for as long as the socket stays open, not just until
# the next login.
REAUTH_INTERVAL_SECONDS = 60.0


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, ticket: str | None = None) -> None:
    if not ticket:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing ticket")

    ticket_store = websocket.app.state.ws_ticket_store
    identity = ticket_store.consume(ticket)
    if identity is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
    user_id, _role, branch = identity

    ws_manager = websocket.app.state.ws_manager
    await ws_manager.connect(websocket, branch=branch)

    receive_task = asyncio.ensure_future(_drain_incoming(websocket))
    reauth_task = asyncio.ensure_future(_reauthorize_periodically(websocket, user_id, branch))
    try:
        await asyncio.wait({receive_task, reauth_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (receive_task, reauth_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        ws_manager.disconnect(websocket)


async def _drain_incoming(websocket: WebSocket) -> None:
    """Clients don't send data; just keep the connection open and detect
    disconnects promptly."""
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


async def _reauthorize_periodically(websocket: WebSocket, user_id: str, branch: str | None) -> None:
    """Closes the connection if the account behind it was deleted, or its
    branch scope changed, since the handshake. Runs for as long as the
    connection is open; the finally block in ws_live cancels it on any exit
    path (client disconnect, send failure, or this closing the socket
    itself)."""
    from app.models.user import User

    while True:
        await asyncio.sleep(REAUTH_INTERVAL_SECONDS)
        async with db_module.AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
        if user is None or user.branch != branch:
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access revoked")
            return
