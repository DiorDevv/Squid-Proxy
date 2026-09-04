export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatTime(iso: string): string {
  const date = new Date(iso)
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return '0m'
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  if (hours > 0) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
  if (minutes > 0) return `${minutes}m`
  return `${Math.floor(totalSeconds)}s`
}

/** `datetime-local` inputs want "YYYY-MM-DDTHH:mm" in local time, with no
 * timezone suffix -- deliberately *not* toISOString() (which is UTC and
 * would show the wrong local clock time in the picker). */
export function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffSeconds = Math.max(0, Math.floor(diffMs / 1000))

  if (diffSeconds < 5) return 'just now'
  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

/** Response-time latency from the Analytics per-minute histogram. Its top
 * band is unbounded ("≥10s"), so any percentile that lands at or past
 * 10000ms is shown as "≥10s" rather than a spuriously precise "10.0s" --
 * the data genuinely can't distinguish beyond that. */
export function formatLatencyMs(ms: number): string {
  if (ms >= 10000) return '≥10s'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}
