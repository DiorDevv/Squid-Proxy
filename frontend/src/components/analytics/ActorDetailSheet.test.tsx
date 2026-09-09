import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ActorDetailSheet } from '@/components/analytics/ActorDetailSheet'
import type { ActorDetailResponse, ActorRow } from '@/types/api'

const DETAIL: ActorDetailResponse = {
  actor: '10.0.0.5',
  is_user: false,
  first_seen: null,
  last_seen: null,
  request_count: 300,
  blocked_count: 12,
  total_bytes: 9000,
  bytes_received: 1200,
  hourly: Array<number>(24).fill(0),
  top_domains: [],
  denied_domains: [],
  categories: [
    {
      category: 'news',
      request_count: 200,
      total_bytes: 6000,
      bytes_received: 900,
      domains: [
        { domain: 'cnn.com', category: 'news', request_count: 150, blocked_count: 0, total_bytes: 4000, bytes_received: 700 },
        { domain: 'bbc.com', category: 'news', request_count: 50, blocked_count: 2, total_bytes: 2000, bytes_received: 200 },
      ],
    },
    {
      category: 'social_media',
      request_count: 100,
      total_bytes: 3000,
      bytes_received: 100,
      domains: [
        { domain: 'x.com', category: 'social_media', request_count: 100, blocked_count: 0, total_bytes: 3000, bytes_received: 100 },
      ],
    },
  ],
}

vi.mock('@/hooks/useAnalytics', () => ({
  useActorDetail: () => ({ data: DETAIL, isLoading: false }),
}))
vi.mock('@/lib/auth-store', () => ({
  useAuthStore: (selector: (state: { role: string }) => unknown) => selector({ role: 'auditor' }),
}))

const ACTOR: ActorRow = {
  actor: '10.0.0.5',
  is_user: false,
  request_count: 300,
  blocked_count: 12,
  blocked_ratio: 0.04,
  total_bytes: 9000,
  bytes_received: 1200,
  top_category: 'news',
}

describe('ActorDetailSheet', () => {
  it('nests each category over the domains that resolved to it', () => {
    render(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    const newsDetails = screen.getByText('News').closest('details')
    expect(newsDetails).not.toBeNull()
    expect(within(newsDetails as HTMLElement).getByText('cnn.com')).toBeInTheDocument()
    expect(within(newsDetails as HTMLElement).getByText('bbc.com')).toBeInTheDocument()
    // bbc.com had 2 blocked requests -> shows the blocked marker
    expect(within(newsDetails as HTMLElement).getByText('2 ✕')).toBeInTheDocument()

    // a domain from another category is not under News
    expect(within(newsDetails as HTMLElement).queryByText('x.com')).toBeNull()
  })
})
