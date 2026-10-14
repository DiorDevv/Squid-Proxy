import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { connectLiveEvents, type WsConnectionState } from '@/lib/ws-client'
import type { LiveEvent } from '@/types/events'

const MAX_RECONNECT_DELAY_MS = 30_000
const INITIAL_RECONNECT_DELAY_MS = 2_000

interface UseWebSocketResult {
  connectionState: WsConnectionState
  liveEvents: LiveEvent[]
}

/** Aggregate queries whose hooks disable their own REST polling while `live`
 * is true (see useSummary/useTimeseries/useTopDomains/useEvents/useClients/
 * useInsights/useDomainCategories) on the assumption that a live WS
 * connection keeps them fresh. The socket itself only streams into
 * `liveEvents` though -- without this, those cards/charts/lists would just
 * freeze the moment the socket connects. Invalidating by key prefix here
 * covers every (rangeParams, ...) variant already cached, same as
 * useSetDomainCategory's onSuccess does. */
const LIVE_INVALIDATED_QUERY_KEYS = [
  ['summary'],
  ['timeseries'],
  ['top-domains'],
  ['top-blocked'],
  ['top-data-usage'],
  ['usage-by-category'],
  ['events'],
  ['clients'],
  ['insights-recent'],
]

// Throttled (not debounced): a continuous event stream must still refetch
// periodically, not defer forever waiting for a gap between events.
// 15 s, not faster: each tick refetches every key above (a 24h /api/summary
// alone is ~1 s of database time), and with proxy traffic the stream never
// pauses -- at 3 s one open dashboard kept the database busy nonstop.
const INVALIDATE_THROTTLE_MS = 15_000

/**
 * Maintains a /ws/live connection with capped exponential-backoff
 * reconnects. Callers combine `connectionState` with a polling fallback
 * (see useLiveEvents) so the app stays fully functional without WebSockets.
 */
export function useWebSocket(enabled: boolean, maxBuffered = 50): UseWebSocketResult {
  const [connectionState, setConnectionState] = useState<WsConnectionState>('connecting')
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([])
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!enabled) return

    let disposed = false
    let dispose: (() => void) | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let invalidateTimer: ReturnType<typeof setTimeout> | null = null
    // invalidateQueries refetches mounted queries even in a background tab,
    // so a forgotten dashboard tab would keep hammering the API. While the
    // tab is hidden, only remember that data went stale; catch up once on
    // return.
    let missedWhileHidden = false

    function invalidateAll() {
      for (const queryKey of LIVE_INVALIDATED_QUERY_KEYS) {
        queryClient.invalidateQueries({ queryKey })
      }
    }

    function scheduleInvalidate() {
      if (invalidateTimer) return
      invalidateTimer = setTimeout(() => {
        invalidateTimer = null
        if (document.hidden) {
          missedWhileHidden = true
          return
        }
        invalidateAll()
      }, INVALIDATE_THROTTLE_MS)
    }

    function handleVisibilityChange() {
      if (!document.hidden && missedWhileHidden) {
        missedWhileHidden = false
        invalidateAll()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    function start() {
      dispose = connectLiveEvents({
        onEvent: (event) => {
          setLiveEvents((prev) => [event, ...prev].slice(0, maxBuffered))
          scheduleInvalidate()
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
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (invalidateTimer) clearTimeout(invalidateTimer)
      dispose?.()
    }
  }, [enabled, maxBuffered, queryClient])

  return { connectionState, liveEvents }
}
