import { test, expect, type Page, type Locator } from '@playwright/test'

/**
 * E2E coverage for the Settings page -- previously untouched by any spec
 * (smoke.spec.ts only covers login/Dashboard/Blocked/Clients). Follows the
 * same conventions established there: one shared serial session (refresh
 * tokens rotate on use, see smoke.spec.ts's own comment on this), role/
 * label/text selectors only, no manual waits, real backend/no mocking.
 *
 * Precondition: same as smoke.spec.ts -- a running backend with a
 * bootstrapped admin (ADMIN_EMAIL/ADMIN_PASSWORD, override via
 * E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD if needed).
 */

// Scopes every query below to one <Panel>'s own <section> (see
// components/common/Panel.tsx -- a bare <section><h2>{title}</h2>...) since
// Panel itself has no accessible region name of its own to getByRole
// against. This is also what keeps e.g. "Save" (rendered by both
// AlertSettingsPanel and ExportSettingsPanel) and "Download export" from
// colliding with anything else on a page this dense with panels -- the
// exact kind of unscoped-selector collision smoke.spec.ts's own sidebar
// comment already ran into once.
function settingsPanel(page: Page, heading: string): Locator {
  return page.locator('section').filter({ has: page.getByRole('heading', { name: heading, exact: true }) })
}

function uniqueTestEmail(tag: string): string {
  return `e2e-${tag}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`
}

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.com'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'admin12345'

// A real UI login of its own (like smoke.spec.ts's `login` describe does),
// not the shared storageState global-setup.ts saves for the rest of the
// suite -- that file is a static, single-use snapshot (refresh tokens
// rotate on use), so only the *first* independent page to load it can ever
// redeem it. This file's own beforeAll is exactly that kind of second,
// independent consumer, so sharing the file would race smoke.spec.ts's own
// "authenticated" block for the same cookie depending on file execution
// order. Logging in for real here instead makes this file self-contained
// regardless of what other spec files exist or the order they run in.
test.describe.serial('settings page', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let page: Page

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage()
    await page.goto('/login')
    await page.getByLabel('Email', { exact: false }).fill(ADMIN_EMAIL)
    await page.locator('input[type="password"]').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL('/')

    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()
  })

  test.afterAll(async () => {
    await page.close()
  })

  test('every panel renders without tripping the per-panel error boundary', async () => {
    for (const heading of [
      'User management',
      'Audit log',
      'Domain categories',
      'Alert settings',
      'Scheduled reports',
      'Export events',
      'Recent exports',
      'Export cleanup settings',
    ]) {
      await expect(settingsPanel(page, heading)).toBeVisible()
    }
    // PanelErrorBoundary's compact fallback text (see
    // components/common/PanelErrorBoundary.tsx) -- its absence here is a
    // regression check for that feature as much as a load-error check for
    // this page.
    await expect(page.getByText(/couldn't be displayed/i)).not.toBeVisible()
  })

  test('create, change role and branch, then delete a user in User management', async () => {
    const email = uniqueTestEmail('user')
    const panel = settingsPanel(page, 'User management')

    await panel.getByRole('button', { name: 'Add user' }).click()
    const dialog = page.getByRole('dialog', { name: 'Add user' })
    await dialog.getByLabel('Email', { exact: true }).fill(email)
    await dialog.getByLabel('Password', { exact: true }).fill('e2e-test-pass-123')
    await dialog.getByRole('button', { name: 'Create user' }).click()

    await expect(panel.getByText(email)).toBeVisible()

    const row = panel.getByRole('row').filter({ hasText: email })
    await row.getByRole('combobox', { name: `Change role for ${email}` }).click()
    await page.getByRole('option', { name: 'Admin', exact: true }).click()
    await expect(page.getByText(`${email} is now admin.`)).toBeVisible()

    await row.getByRole('combobox', { name: `Change branch access for ${email}` }).click()
    // Real deployment config here has more than one branch, so the picker
    // offers real branch options alongside "All branches" -- pick whichever
    // real branch sorts first rather than hardcoding one of this
    // environment's specific branch names.
    const branchOptions = page.getByRole('option').filter({ hasNotText: 'All branches' })
    const firstBranchLabel = (await branchOptions.first().textContent()) ?? ''
    await branchOptions.first().click()
    await expect(page.getByText(`Branch access updated for ${email}.`)).toBeVisible()
    if (firstBranchLabel) {
      await expect(row.getByRole('combobox', { name: `Change branch access for ${email}` })).toContainText(
        firstBranchLabel,
      )
    }

    await row.getByRole('button', { name: `Delete ${email}` }).click()
    await page.getByRole('button', { name: 'Delete account' }).click()
    await expect(page.getByText(`${email} removed.`)).toBeVisible()
    await expect(panel.getByText(email)).not.toBeVisible()
  })

  test('update and persist an alert threshold, then restore it', async () => {
    const panel = settingsPanel(page, 'Alert settings')
    const input = panel.getByLabel('Non-work time threshold (minutes/day)')

    const originalValue = await input.inputValue()
    // Deliberately different from whatever it currently is, so the
    // reload-and-reread check below can't pass by coincidence.
    const newValue = String((Number(originalValue) || 0) + 7)

    await input.fill(newValue)
    await panel.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText('Alert settings saved.')).toBeVisible()

    await page.reload()
    await expect(settingsPanel(page, 'Alert settings').getByLabel('Non-work time threshold (minutes/day)')).toHaveValue(
      newValue,
    )

    // Restore -- this suite shouldn't leave a real admin-facing setting
    // permanently drifted just from having run once.
    const restorePanel = settingsPanel(page, 'Alert settings')
    await restorePanel.getByLabel('Non-work time threshold (minutes/day)').fill(originalValue)
    await restorePanel.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText('Alert settings saved.')).toBeVisible()
  })

  test('triggering an export job surfaces it in Recent exports', async () => {
    const exportPanel = settingsPanel(page, 'Export events')
    const recentPanel = settingsPanel(page, 'Recent exports')

    const rowsBefore = await recentPanel.getByRole('row').count()

    await exportPanel.getByRole('button', { name: 'Download export' }).click()
    // The button's own label flips to "Preparing export…" while active
    // (see SettingsPage.tsx's exportButtonLabel) -- waiting for it to leave
    // that state is a data-agnostic proxy for "the job reached a terminal
    // status" without asserting which one, since done/failed/cancelled are
    // all valid depending on real backend state.
    await expect(exportPanel.getByRole('button', { name: /preparing export/i })).not.toBeVisible({
      timeout: 30_000,
    })

    await expect(async () => {
      expect(await recentPanel.getByRole('row').count()).toBeGreaterThan(rowsBefore)
    }).toPass({ timeout: 10_000 })
    await expect(
      recentPanel.getByText(/pending|running|done|failed|cancelled/i).first(),
    ).toBeVisible()
  })

  test('Scheduled reports and Audit log panels reflect real activity', async () => {
    await expect(settingsPanel(page, 'Scheduled reports')).toBeVisible()

    // The user-create/role-change/branch-change/delete sequence from the
    // earlier test in this same serial run is real activity this suite
    // itself produced -- asserting on it (rather than on unrelated
    // pre-existing data) keeps this test meaningful whether or not the
    // environment has any other audit history.
    const auditPanel = settingsPanel(page, 'Audit log')
    await expect(auditPanel.getByRole('table')).toBeVisible()
    await expect(auditPanel.getByText(/user created/i).first()).toBeVisible()
    await expect(auditPanel.getByText(/user deleted/i).first()).toBeVisible()
  })
})
