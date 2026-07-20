import { request as playwrightRequest } from '@playwright/test'

const API_BASE_URL = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000'
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.com'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'admin12345'

export const STORAGE_STATE_PATH = 'e2e/.auth/state.json'

/** Logs in once via the API (not the UI) and saves the resulting httpOnly
 * refresh-token cookie so every test in the "authenticated" describe block
 * starts already signed in -- the app's bootstrap() silently exchanges
 * that cookie for a fresh in-memory access token on load (see
 * lib/auth-store.ts's comment on /api/auth/refresh). This keeps the whole
 * suite to a single POST /api/auth/login instead of one per test, which
 * matters because the endpoint is rate-limited (LOGIN_RATE_LIMIT, 5/minute
 * by default) -- one login per spec would burn through that budget fast. */
export default async function globalSetup() {
  const context = await playwrightRequest.newContext({ baseURL: API_BASE_URL })
  const response = await context.post('/api/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  })
  if (!response.ok()) {
    throw new Error(
      `E2E global setup: login failed (${response.status()}). Is the backend running at ${API_BASE_URL}? ` +
        'Override with E2E_API_BASE_URL / E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD if your setup differs.',
    )
  }
  await context.storageState({ path: STORAGE_STATE_PATH })
  await context.dispose()
}
