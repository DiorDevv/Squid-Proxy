import { createContext, useContext } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { LiveEvent } from '@/types/events'
import type { WsConnectionState } from '@/lib/ws-client'

interface LiveEventsValue {
  events: LiveEvent[]
  connectionState: WsConnectionState
  isLoading: boolean
  pollingError: boolean
}

/** WebSocket-first recent-events feed with a REST polling fallback so the
 * dashboard stays functional even when /ws/live can't connect. Call once
 * (see LiveEventsContext) and share via context -- every consumer reading
 * from the same socket instead of each opening its own. */
export function useLiveEventsSource(limit = 50): LiveEventsValue {
  const { connectionState, liveEvents } = useWebSocket(true, limit)
  const isLive = connectionState === 'open'

  const pollingQuery = useQuery({
    queryKey: ['events-recent-poll', limit],
    queryFn: () => apiFetch<LiveEvent[]>('/api/events/recent', { searchParams: { limit } }),
    refetchInterval: isLive ? false : POLLING_FALLBACK_INTERVAL_MS,
  })

  const events = isLive && liveEvents.length > 0 ? liveEvents : (pollingQuery.data ?? [])

  return {
    events,
    connectionState,
    isLoading: pollingQuery.isLoading && events.length === 0,
    pollingError: pollingQuery.isError,
  }
}

export const LiveEventsContext = createContext<LiveEventsValue | null>(null)

export function useLiveEvents(): LiveEventsValue {
  const ctx = useContext(LiveEventsContext)
  if (!ctx) throw new Error('useLiveEvents must be used within LiveEventsContext.Provider')
  return ctx
}
