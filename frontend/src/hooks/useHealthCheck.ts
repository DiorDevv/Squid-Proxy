import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { HealthResponse } from '@/types/api'

const POLL_INTERVAL_MS = 30_000

/** A real Squid install whose access_log directive uses a logformat other
 * than "squid" (e.g. "combined") produces a tailer that looks perfectly
 * healthy -- the file exists, is being read -- while every line fails to
 * parse, silently leaving the whole dashboard empty. This is the one signal
 * that tells the difference, so it's polled globally rather than only
 * exposed via /api/health for anyone who thinks to check. */
export function useHealthCheck() {
  return useQuery({
    queryKey: ['health-check'],
    queryFn: () => apiFetch<HealthResponse>('/api/health'),
    refetchInterval: POLL_INTERVAL_MS,
    retry: false,
  })
}
