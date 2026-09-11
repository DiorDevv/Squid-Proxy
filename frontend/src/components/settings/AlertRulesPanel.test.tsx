import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { AlertRulesPanel } from '@/components/settings/AlertRulesPanel'
import * as apiClient from '@/lib/api-client'
import type { AlertRuleOut } from '@/types/api'

const RULE: AlertRuleOut = {
  id: 1,
  branch: 'default',
  name: 'IP data spike',
  scope: 'client_ip',
  metric: 'total_bytes',
  window_minutes: 10,
  threshold: 50_000_000,
  severity: 'high',
  enabled: true,
  updated_at: '2026-09-11T10:00:00Z',
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AlertRulesPanel branch="default" />
    </QueryClientProvider>,
  )
}

describe('AlertRulesPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('lists existing rules with formatted threshold, scope, metric and severity', async () => {
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string) => {
      if (path === '/api/alert-settings/rules') return [RULE] as unknown
      throw new Error(`unexpected ${path}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('IP data spike')).toBeInTheDocument())
    expect(screen.getByText('Client IP')).toBeInTheDocument()
    expect(screen.getByText('Data downloaded')).toBeInTheDocument()
    expect(screen.getByText('47.7 MB')).toBeInTheDocument() // formatBytes(50_000_000)
    expect(screen.getByText('10 min')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('shows the empty state when there are no rules', async () => {
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string) => {
      if (path === '/api/alert-settings/rules') return [] as unknown
      throw new Error(`unexpected ${path}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('No custom rules yet.')).toBeInTheDocument())
  })

  it('creates a new rule from the add-rule dialog', async () => {
    const user = userEvent.setup()
    let created: unknown = null
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string, options?: { method?: string; body?: unknown }) => {
      if (path === '/api/alert-settings/rules' && (!options || options.method === undefined)) return [] as unknown
      if (path === '/api/alert-settings/rules' && options?.method === 'POST') {
        created = options.body
        return { ...RULE, id: 2, ...(options.body as object) } as unknown
      }
      throw new Error(`unexpected ${path} ${options?.method}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('No custom rules yet.')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /add rule/i }))
    await user.type(screen.getByLabelText('Name'), 'Domain spike')
    await user.clear(screen.getByLabelText(/threshold/i))
    await user.type(screen.getByLabelText(/threshold/i), '100')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(created).not.toBeNull())
    expect((created as { name: string }).name).toBe('Domain spike')
  })

  it('deletes a rule after confirming', async () => {
    const user = userEvent.setup()
    let deleted = false
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === '/api/alert-settings/rules' && options?.method === undefined) {
        return (deleted ? [] : [RULE]) as unknown
      }
      if (path === '/api/alert-settings/rules/1' && options?.method === 'DELETE') {
        deleted = true
        return undefined as unknown
      }
      throw new Error(`unexpected ${path} ${options?.method}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('IP data spike')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' })) // confirm

    await waitFor(() => expect(deleted).toBe(true))
  })
})
