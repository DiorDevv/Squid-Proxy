import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ActivityHeatmap } from '@/components/analytics/ActivityHeatmap'
import type { ActivityHeatmapResponse } from '@/types/api'

describe('ActivityHeatmap', () => {
  it('renders the empty state when there are no cells', () => {
    const data: ActivityHeatmapResponse = { blocked_only: false, tz_offset_minutes: 0, max_value: 0, cells: [] }
    render(<ActivityHeatmap data={data} />)
    expect(screen.getByText('No activity recorded in this range.')).toBeInTheDocument()
  })

  it('labels the note "UTC" for a zero offset', () => {
    const data: ActivityHeatmapResponse = {
      blocked_only: false,
      tz_offset_minutes: 0,
      max_value: 50,
      cells: [{ weekday: 2, hour: 14, value: 50 }],
    }
    render(<ActivityHeatmap data={data} />)
    expect(screen.getByText('Times shown in UTC.')).toBeInTheDocument()
    expect(screen.getByTitle(/Wed 14:00 UTC — 50/)).toBeInTheDocument()
  })

  it('formats a positive offset as UTC+HH:MM', () => {
    const data: ActivityHeatmapResponse = {
      blocked_only: true,
      tz_offset_minutes: 300,
      max_value: 10,
      cells: [{ weekday: 0, hour: 9, value: 10 }],
    }
    render(<ActivityHeatmap data={data} />)
    expect(screen.getByText('Times shown in UTC+05:00.')).toBeInTheDocument()
  })

  it('falls back to plain "UTC" when the offset field is missing', () => {
    const data = {
      blocked_only: false,
      max_value: 5,
      cells: [{ weekday: 1, hour: 8, value: 5 }],
    } as unknown as ActivityHeatmapResponse
    render(<ActivityHeatmap data={data} />)
    expect(screen.getByText('Times shown in UTC.')).toBeInTheDocument()
  })
})
