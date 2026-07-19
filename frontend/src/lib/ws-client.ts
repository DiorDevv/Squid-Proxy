import { WS_BASE_URL } from '@/lib/constants'
import { api } from '@/lib/api-client'
import type { LiveEvent } from '@/types/events'

export type WsConnectionState = 'connecting' | 'open' | 'closed'

function resolveWsBaseUrl(): string {
  // WS_BASE_URL may be relative ("" in the Docker image, where nginx proxies
  // /ws on the same origin) or absolute (e.g. "ws://localhost:8000" in dev).
  if (WS_BASE_URL) return WS_BASE_URL
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

interface LiveEventSocketHandlers {
  onEvent: (event: LiveEvent) => void
  onStateChange: (state: WsConnectionState) => void
}

/**
 * Opens /ws/live using a short-lived single-use ticket obtained via a normal
 * authenticated REST call, so the real access token never appears in a URL
 * (see backend app/core/security.py:WsTicketStore). Returns a disposer.
 */
export function connectLiveEvents(handlers: LiveEventSocketHandlers): () => void {
  let socket: WebSocket | null = null
  let disposed = false

  async function connect() {
    handlers.onStateChange('connecting')
    let ticket: string
    try {
      const response = await api.wsTicket()
      ticket = response.ticket
    } catch {
      handlers.onStateChange('closed')
      return
    }
    if (disposed) return

    const wsUrl = `${resolveWsBaseUrl()}/ws/live?ticket=${encodeURIComponent(ticket)}`
    socket = new WebSocket(wsUrl)

    socket.onopen = () => handlers.onStateChange('open')
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as LiveEvent
        handlers.onEvent(parsed)
      } catch {
        // ignore malformed frames
      }
    }
    socket.onclose = () => {
      if (!disposed) handlers.onStateChange('closed')
    }
    socket.onerror = () => {
      socket?.close()
    }
  }

  connect()

  return () => {
    disposed = true
    socket?.close()
  }
}
