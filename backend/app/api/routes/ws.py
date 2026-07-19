import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, status

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, ticket: str | None = None) -> None:
    if not ticket:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing ticket")

    ticket_store = websocket.app.state.ws_ticket_store
    identity = ticket_store.consume(ticket)
    if identity is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")

    ws_manager = websocket.app.state.ws_manager
    await ws_manager.connect(websocket)
    try:
        while True:
            # Clients don't send data; just keep the connection open and
            # detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)
