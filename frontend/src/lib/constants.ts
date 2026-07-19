// In a production build served behind nginx (see deploy/nginx and the
// Dockerfile), leaving these unset is *intentional* -- it means "same
// origin as the page", not "point at localhost". Only warn, don't fall
// back to a hardcoded localhost value in that case; a same-origin relative
// path ('') is the correct production default. The localhost fallback below
// only fires in dev, where Vite's env is never PROD.
if (import.meta.env.PROD && !import.meta.env.VITE_API_BASE_URL && !import.meta.env.VITE_WS_URL) {
  console.warn(
    '[squid-dashboard] VITE_API_BASE_URL / VITE_WS_URL are unset in this production build. ' +
      'Assuming same-origin (correct for the bundled nginx deploy); if this build is served ' +
      'standalone against a remote API, set both at build time.',
  )
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000')
export const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? (import.meta.env.PROD ? '' : 'ws://localhost:8000')

export const POLLING_FALLBACK_INTERVAL_MS = 10_000

export const RANGE_OPTIONS = [
  { value: '1h', label: '1h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
] as const
