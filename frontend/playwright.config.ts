import { defineConfig, devices } from '@playwright/test'
import { STORAGE_STATE_PATH } from './e2e/global-setup'

/** Smoke-level E2E suite against the real, wired-together app. This config
 * only manages the frontend dev server -- the backend (with a bootstrapped
 * admin user) is a precondition, started the same way the project's README
 * already documents for local dev. See e2e/smoke.spec.ts for the exact
 * precondition and how to override the admin credentials, and
 * e2e/global-setup.ts for why authentication happens once, up front. */
export default defineConfig({
  testDir: './e2e',
  // Every spec file shares the *one* refresh-token cookie global-setup.ts
  // saves (see its own docstring on why: avoiding the login rate limit).
  // Refresh tokens rotate on use, so two files' "authenticated" describe
  // blocks both calling bootstrap() at the same time -- which fullyParallel
  // (or any workers > 1) allows across files, not just within one -- race
  // to redeem the same cookie; whichever loses gets bounced to /login and
  // every test in that file fails. Single-worker execution keeps the whole
  // suite to one continuous session, matching what global-setup's own
  // single up-front login already assumes.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    storageState: STORAGE_STATE_PATH,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
})
