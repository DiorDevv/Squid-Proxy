import { test, expect, type Page } from '@playwright/test'

/**
 * Smoke suite against the real, wired-together app -- the same golden
 * paths verified by hand throughout this project's development (login,
 * dashboard, Blocked, Clients).
 *
 * Precondition: the backend must already be running and reachable (default
 * assumed at http://localhost:8000, override with E2E_API_BASE_URL) with
 * an admin user bootstrapped (this happens automatically on first backend
 * startup from ADMIN_EMAIL/ADMIN_PASSWORD -- see README.md). Playwright
 * only manages the frontend dev server (see playwright.config.ts's
 * webServer block) and authenticates once up front (see global-setup.ts).
 *
 * Override credentials with E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD env vars
 * if your backend wasn't bootstrapped with the documented dev defaults.
 */
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.com'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'admin12345'

// Whether the backend has any matching events or not, a page must reach a
// settled state that is neither a loading skeleton nor an error -- data
// presence itself isn't asserted, so this passes against an empty backend
// (no demo generator) just as well as a seeded one.
async function expectPageLoadedWithoutError(page: Page) {
  await expect(page.getByRole('button', { name: 'Retry' })).not.toBeVisible()
  await expect(page.getByRole('table').or(page.getByText(/no .* (recorded|found)/i))).toBeVisible()
}

test.describe('login', () => {
  // These two tests exercise the login form itself, so they must start
  // unauthenticated -- overrides the project-wide storageState (see
  // playwright.config.ts) which every other test relies on to skip login.
  test.use({ storageState: { cookies: [], origins: [] } })

  test('successful login reaches the dashboard', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email', { exact: false }).fill(ADMIN_EMAIL)
    await page.locator('input[type="password"]').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible()
  })

  test('failed login shows an error and stays on the login page', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email', { exact: false }).fill(ADMIN_EMAIL)
    await page.locator('input[type="password"]').fill('definitely-the-wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })
})

// Refresh tokens rotate on every use (see README's security notes), so the
// one refresh-token cookie global-setup saved can only be redeemed once --
// running these tests in Playwright's default one-fresh-context-per-test
// mode would have each test's own page load independently try to consume
// the same now-already-rotated cookie, and all but the first would fail
// bootstrap() and bounce to /login. Sharing a single page (and therefore a
// single bootstrap/refresh) across the group, navigating between pages the
// same way a real user clicking around one open tab would, sidesteps that
// entirely instead of needing a login (and its rate limit) per test.
test.describe.serial('authenticated', () => {
  let page: Page

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage()
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible()
  })

  test.afterAll(async () => {
    await page.close()
  })

  test('Blocked page renders its filters and reaches a loaded state', async () => {
    await page.getByRole('link', { name: 'Blocked' }).click()

    await expect(page.getByRole('heading', { name: 'Blocked events', level: 1 })).toBeVisible()
    // Range selector (1h/24h/7d/Custom) is the new date-range control this
    // page didn't have before -- confirms the DB-backed rewrite is live.
    await expect(page.getByRole('button', { name: '24h' })).toBeVisible()
    await expectPageLoadedWithoutError(page)
  })

  test('Clients page renders its table and reaches a loaded state', async () => {
    await page.getByRole('link', { name: 'Clients' }).click()

    await expect(page.getByRole('heading', { name: 'Clients', level: 1 })).toBeVisible()
    await expectPageLoadedWithoutError(page)
  })
})
