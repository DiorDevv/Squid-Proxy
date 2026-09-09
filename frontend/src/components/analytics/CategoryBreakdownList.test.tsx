import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CategoryBreakdownList } from '@/components/analytics/CategoryBreakdownList'
import type { CategoryTrendResponse } from '@/types/api'

const useTopDomains = vi.hoisted(() => vi.fn())
vi.mock('@/hooks/useTopDomains', () => ({ useTopDomains }))

const DATA: CategoryTrendResponse = {
  granularity: 'hour',
  metric: 'requests',
  categories: ['shopping', 'gaming'],
  points: [
    { bucket_ts: '2026-01-01T00:00:00Z', values: { shopping: 30, gaming: 5 } },
    { bucket_ts: '2026-01-01T01:00:00Z', values: { shopping: 20, gaming: 5 } },
  ],
}

describe('CategoryBreakdownList', () => {
  it('expands a category to its domains, fetched only on open', async () => {
    useTopDomains.mockReturnValue({
      isLoading: false,
      data: {
        items: [
          { domain: 'amazon.com', category: 'shopping', request_count: 40, blocked_count: 0, total_bytes: 1000 },
          { domain: 'ebay.com', category: 'shopping', request_count: 10, blocked_count: 3, total_bytes: 500 },
        ],
      },
    })
    render(<CategoryBreakdownList data={DATA} rangeParams={{}} />)

    // nothing fetched until a row opens
    expect(useTopDomains).not.toHaveBeenCalled()
    expect(screen.queryByText('amazon.com')).toBeNull()

    // shopping (50 total) sorts above gaming (10)
    const shopping = screen.getByRole('button', { name: /shopping/i })
    await userEvent.click(shopping)

    expect(useTopDomains).toHaveBeenCalledWith({}, 10, true, 'shopping')
    expect(screen.getByText('amazon.com')).toBeInTheDocument()
    expect(screen.getByText('ebay.com')).toBeInTheDocument()
    expect(screen.getByText('3 ✕')).toBeInTheDocument()
  })
})
