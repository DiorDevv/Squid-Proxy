import { useEffect, useRef, useState } from 'react'
import { connectLiveEvents, type WsConnectionState } from '@/lib/ws-client'
import type { LiveEvent } from '@/types/events'

const MAX_RECONNECT_DELAY_MS = 30_000
const INITIAL_RECONNECT_DELAY_MS = 2_000

interface UseWebSocketResult {
  connectionState: WsConnectionState
  liveEvents: LiveEvent[]
}

/**
 * Maintains a /ws/live connection with capped exponential-backoff
 * reconnects. Callers combine `connectionState` with a polling fallback
 * (see useLiveEvents) so the app stays fully functional without WebSockets.
 */
export function useWebSocket(enabled: boolean, maxBuffered = 50): UseWebSocketResult {
  const [connectionState, setConnectionState] = useState<WsConnectionState>('connecting')
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([])
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS)

  useEffect(() => {
    if (!enabled) return

    let disposed = false
    let dispose: (() => void) | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function start() {
      dispose = connectLiveEvents({
        onEvent: (event) => {
          setLiveEvents((prev) => [event, ...prev].slice(0, maxBuffered))
        },
        onStateChange: (state) => {
          if (disposed) return
          setConnectionState(state)
          if (state === 'open') {
            reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS
          } else if (state === 'closed') {
            scheduleReconnect()
          }
        },
      })
    }

    function scheduleReconnect() {
      if (disposed || reconnectTimer) return
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (!disposed) {
          dispose?.()
          start()
        }
      }, reconnectDelayRef.current)
      reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, MAX_RECONNECT_DELAY_MS)
    }

    start()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      dispose?.()
    }
  }, [enabled, maxBuffered])

  return { connectionState, liveEvents }
}
