import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import SettingsRetentionPage from '@/pages/settings/SettingsRetentionPage'
import type { RetentionSettingsOut } from '@/types/api'

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api-client', () => ({ apiFetch }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const CURRENT: RetentionSettingsOut = {
  raw_events_days: 14,
  halt_purge_if_archive_lag_days: null,
  updated_at: new Date().toISOString(),
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SettingsRetentionPage />
    </QueryClientProvider>,
  )
}

describe('SettingsRetentionPage', () => {
  beforeEach(() => apiFetch.mockReset())

  it('saves a raised window straight away (no confirm)', async () => {
    apiFetch.mockImplementation((_url: string, opts?: { method?: string }) =>
      opts?.method === 'PUT'
        ? Promise.resolve({ ...CURRENT, raw_events_days: 30 })
        : Promise.resolve(CURRENT),
    )
    renderPage()
    const input = await screen.findByLabelText(/Keep raw_events for/i)
    await userEvent.clear(input)
    await userEvent.type(input, '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/retention-settings',
      expect.objectContaining({ method: 'PUT', body: { raw_events_days: 30, halt_purge_if_archive_lag_days: null } }),
    )
  })

  it('confirms before lowering the window', async () => {
    apiFetch.mockImplementation((_url: string, opts?: { method?: string }) =>
      opts?.method === 'PUT'
        ? Promise.resolve({ ...CURRENT, raw_events_days: 7 })
        : Promise.resolve(CURRENT),
    )
    renderPage()
    const input = await screen.findByLabelText(/Keep raw_events for/i)
    await userEvent.clear(input)
    await userEvent.type(input, '7')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    // dialog appears; PUT not sent yet
    expect(await screen.findByText('Shorten the retention window?')).toBeInTheDocument()
    expect(apiFetch).not.toHaveBeenCalledWith('/api/retention-settings', expect.objectContaining({ method: 'PUT' }))

    await userEvent.click(screen.getByRole('button', { name: 'Shorten and delete' }))
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/retention-settings',
      expect.objectContaining({ method: 'PUT', body: expect.objectContaining({ raw_events_days: 7 }) }),
    )
  })
})
