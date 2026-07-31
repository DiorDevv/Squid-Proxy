/** Given the resolved `since`/`until` window of the *current* period (as
 * returned by /api/summary -- so it reflects whatever the range preset or
 * custom range actually resolved to, without this module needing to know
 * that logic itself), returns the query params for the immediately
 * preceding period of the same duration, in the same shape
 * useRangeSearchParams produces (from_ts/to_ts + optional branch) so it can
 * be passed straight into useSummary. */
export function getPreviousPeriodParams(
  since: string,
  until: string,
  branch: string | null,
): Record<string, string> {
  const sinceMs = new Date(since).getTime()
  const untilMs = new Date(until).getTime()
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
