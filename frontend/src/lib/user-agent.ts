/** "Chrome · Windows"-style label for a session's User-Agent -- a rough
 * heuristic for recognising one's own devices, not for anything security
 * relevant. Falls back to the raw string when nothing matches. */
export function describeUserAgent(userAgent: string | null): string {
  if (!userAgent) return '—'
  const browser =
    [
      [/Edg\//, 'Edge'],
      [/OPR\//, 'Opera'],
      [/Firefox\//, 'Firefox'],
      [/Chrome\//, 'Chrome'],
      [/Safari\//, 'Safari'],
      [/curl\//, 'curl'],
    ].find(([re]) => (re as RegExp).test(userAgent))?.[1] ?? null
  const os =
    [
      [/Windows/, 'Windows'],
      [/Android/, 'Android'],
      [/iPhone|iPad/, 'iOS'],
      [/Mac OS X/, 'macOS'],
      [/Linux/, 'Linux'],
    ].find(([re]) => (re as RegExp).test(userAgent))?.[1] ?? null
  if (!browser && !os) return userAgent
  return [browser, os].filter(Boolean).join(' · ')
}
