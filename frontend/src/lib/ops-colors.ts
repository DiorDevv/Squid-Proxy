/** Fixed, brand-stable colors for the Squid-operational views. Squid
 * result codes read semantically: cache hits green, misses amber, denies
 * red, tunnels purple, everything else slate. */
export function resultCodeColor(action: string): string {
  const a = action.toUpperCase()
  if (a.includes('DENIED')) return '#ef4444'
  if (a.includes('TUNNEL')) return '#a855f7'
  if (a.includes('HIT') || a.includes('REFRESH_UNMODIFIED')) return '#22c55e'
  if (a.includes('MISS') || a.includes('REFRESH_MODIFIED')) return '#f59e0b'
  return '#64748b'
}

export function statusClassColor(cls: string): string {
  if (cls.startsWith('2')) return '#22c55e'
  if (cls.startsWith('3')) return '#3b82f6'
  if (cls.startsWith('4')) return '#f59e0b'
  if (cls.startsWith('5')) return '#ef4444'
  return '#64748b'
}

export const DENIAL_REASON_COLORS = {
  acl_denied: '#ef4444',
  proxy_auth: '#f59e0b',
  other_blocked: '#a855f7',
} as const

/** Response-time band -> color, fast (green) to slow (red). */
export function durationBandColor(label: string): string {
  const palette: Record<string, string> = {
    '<100ms': '#22c55e',
    '100-300ms': '#84cc16',
    '300ms-1s': '#f59e0b',
    '1-3s': '#f97316',
    '3-10s': '#ef4444',
    '>=10s': '#b91c1c',
  }
  return palette[label] ?? '#64748b'
}
