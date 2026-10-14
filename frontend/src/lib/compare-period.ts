const MINUTE_MS = 60_000

/** Given the resolved `since`/`until` window of the *current* period (as
 * returned by /api/summary -- so it reflects whatever the range preset or
 * custom range actually resolved to, without this module needing to know
 * that logic itself), returns the query params for the immediately
 * preceding period of the same duration, in the same shape
 * useRangeSearchParams produces (from_ts/to_ts + optional branch) so it can
 * be passed straight into useSummary.
 *
 * Both edges are snapped to whole minutes (the aggregates' own resolution):
 * a rolling range like "24h" resolves to a slightly later since/until on
 * every refetch, and unrounded params would make each refetch a brand-new
 * query key -- i.e. a fresh, uncached previous-period request every time. */
export function getPreviousPeriodParams(
  since: string,
  until: string,
  branch: string | null,
): Record<string, string> {
  const sinceMs = Math.floor(new Date(since).getTime() / MINUTE_MS) * MINUTE_MS
  const untilMs = Math.floor(new Date(until).getTime() / MINUTE_MS) * MINUTE_MS
  const durationMs = untilMs - sinceMs

  const prevUntil = new Date(sinceMs).toISOString()
  const prevSince = new Date(sinceMs - durationMs).toISOString()

  return branch ? { from_ts: prevSince, to_ts: prevUntil, branch } : { from_ts: prevSince, to_ts: prevUntil }
}

/** Percentage change from `previous` to `current`, or null when it can't be
 * expressed meaningfully (no previous-period data yet, or previous was 0 --
 * dividing by zero would produce Infinity/NaN badges). */
export function getPercentChange(current: number, previous: number | undefined): number | null {
  if (previous === undefined || previous === 0) return null
  return ((current - previous) / previous) * 100
}
