import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import SettingsSystemHealthPage from '@/pages/settings/SettingsSystemHealthPage'
import type { SystemHealthResponse } from '@/types/api'

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api-client', () => ({ apiFetch }))

const BASE: SystemHealthResponse = {
  generated_at: new Date().toISOString(),
  database: {
    dialect: 'postgresql',
    total_bytes: 15_000_000_000,
    tables: [{ name: 'raw_events', bytes: 14_000_000_000 }],
    raw_events_oldest: new Date(Date.now() - 14 * 86400_000).toISOString(),
    raw_events_newest: new Date().toISOString(),
    raw_events_row_count: 31_000_000,
    raw_events_added_24h: 2_000_000,
  },
  disk: { path: '/app/archives', total_bytes: 100, free_bytes: 5, used_pct: 95 },
  ingestion: {
    branches: [
      {
        branch: 'main',
        tailer_alive: true,
        lines_seen: 10,
        lines_parsed: 10,
        parse_failure_rate: 0,
        last_event_at: null, // dark branch
      },
    ],
    aggregator_backlog_ratio: 0.1,
    aggregator_events_likely_lost: false,
    unarchived_purge_branches: [],
  },
  background_jobs: [
    {
      name: 'retention-job',
      alive: true,
      last_run_at: new Date().toISOString(),
      last_error: null,
      last_error_at: null,
      consecutive_failures: 0,
    },
  ],
  backup: null,
  offsite: null,
  recent_events: [],
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SettingsSystemHealthPage />
    </QueryClientProvider>,
  )
}

describe('SettingsSystemHealthPage', () => {
  beforeEach(() => apiFetch.mockReset())

  it('renders the panels from the snapshot', async () => {
    apiFetch.mockResolvedValue(BASE)
    renderPage()
    expect(await screen.findByText('Database backup')).toBeInTheDocument()
    expect(screen.getByText('raw_events')).toBeInTheDocument()
    expect(screen.getByText('retention-job')).toBeInTheDocument()
    // backup panel with no file -> "no data" message, not a crash
    expect(screen.getByText(/No backup status available/i)).toBeInTheDocument()
    expect(screen.getByText('No operational failures recorded.')).toBeInTheDocument()
  })

  it('handles a disabled off-site and a dark branch without crashing', async () => {
    apiFetch.mockResolvedValue({
      ...BASE,
      offsite: { ...(BASE.offsite ?? {}), enabled: false } as SystemHealthResponse['offsite'],
    })
    renderPage()
    expect(await screen.findByText('Off-site replication is not configured.')).toBeInTheDocument()
    // dark branch (last_event_at null) still renders its row
    expect(screen.getByText('main')).toBeInTheDocument()
  })
})
