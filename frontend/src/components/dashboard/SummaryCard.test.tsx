import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Gauge } from 'lucide-react'
import { SummaryCard } from '@/components/dashboard/SummaryCard'

describe('SummaryCard', () => {
  // Regression coverage for the bug where a null value (e.g. cache hit rate
  // with no cacheable traffic in range) was coerced to 0 by the caller and
  // rendered as a misleading "0%" -- null must render as a dash instead.
  it('renders a dash, not the formatted zero, when value is null', () => {
    render(
      <SummaryCard
        label="Cache hit rate"
        value={null}
        icon={Gauge}
        noDataLabel="No cacheable traffic in this range"
        formatValue={(v) => `${v}%`}
      />,
    )
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.getByText('—')).toHaveAttribute('title', 'No cacheable traffic in this range')
  })

  it('renders the formatted value when value is a real number, including zero', () => {
    render(<SummaryCard label="Blocked" value={0} icon={Gauge} formatValue={(v) => `${v}%`} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('omits the delta badge when value is null even if deltaPercent is set', () => {
    render(<SummaryCard label="Cache hit rate" value={null} icon={Gauge} deltaPercent={12.5} />)
    expect(screen.queryByText(/12\.5%/)).not.toBeInTheDocument()
  })
})
