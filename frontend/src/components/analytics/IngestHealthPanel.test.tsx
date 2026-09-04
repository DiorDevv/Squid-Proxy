import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IngestHealthPanel } from '@/components/analytics/IngestHealthPanel'
import type { IngestHealthResponse } from '@/types/api'

const DATA: IngestHealthResponse = {
  aggregator_backlog_ratio: 0.05,
  aggregator_events_likely_lost: false,
  branches: [
    { branch: 'hq', tailer_alive: true, parse_failure_rate: 0, lines_seen: 1000, lines_parsed: 1000 },
    { branch: 'wh', tailer_alive: false, parse_failure_rate: 0.8, lines_seen: 500, lines_parsed: 100 },
  ],
}

describe('IngestHealthPanel', () => {
  it('renders a row per branch with tailer state and parse failure rate', () => {
    render(<IngestHealthPanel data={DATA} />)
    expect(screen.getByText('hq')).toBeInTheDocument()
    expect(screen.getByText('wh')).toBeInTheDocument()
    expect(screen.getByText('alive')).toBeInTheDocument()
    expect(screen.getByText('down')).toBeInTheDocument()
    expect(screen.getByText('80.0%')).toHaveClass('text-destructive')
  })

  it('shows the backlog percentage', () => {
    render(<IngestHealthPanel data={DATA} />)
    expect(screen.getByText('5%')).toBeInTheDocument()
  })

  it('flags likely-lost events', () => {
    render(<IngestHealthPanel data={{ ...DATA, aggregator_events_likely_lost: true }} />)
    expect(screen.getByText('events likely lost')).toBeInTheDocument()
  })
})
