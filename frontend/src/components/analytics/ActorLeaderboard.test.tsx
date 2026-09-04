import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ActorLeaderboard } from '@/components/analytics/ActorLeaderboard'
import type { ActorRow } from '@/types/api'

const ROWS: ActorRow[] = [
  {
    actor: 'alice',
    is_user: true,
    request_count: 100,
    blocked_count: 45,
    blocked_ratio: 0.45,
    total_bytes: 5000,
    top_category: 'video_streaming',
    busiest_hour_utc: 14,
  },
]

describe('ActorLeaderboard', () => {
  it('shows the "User" header when actorKind is user', () => {
    render(
      <ActorLeaderboard rows={ROWS} actorKind="user" sort="requests" onSortChange={() => {}} onSelect={() => {}} />,
    )
    expect(screen.getByText('User')).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    // 45% blocked -> destructive tone
    expect(screen.getByText('45.0%')).toHaveClass('text-destructive')
  })

  it('shows the "Client IP" header when actorKind is client_ip', () => {
    render(
      <ActorLeaderboard
        rows={ROWS}
        actorKind="client_ip"
        sort="requests"
        onSortChange={() => {}}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('Client IP')).toBeInTheDocument()
  })

  it('calls onSelect when a row is clicked', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <ActorLeaderboard rows={ROWS} actorKind="user" sort="requests" onSortChange={() => {}} onSelect={onSelect} />,
    )
    await user.click(screen.getByText('alice'))
    expect(onSelect).toHaveBeenCalledWith(ROWS[0])
  })

  it('calls onSortChange from a sortable header', async () => {
    const onSortChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ActorLeaderboard
        rows={ROWS}
        actorKind="user"
        sort="requests"
        onSortChange={onSortChange}
        onSelect={() => {}}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Blocked/ }))
    expect(onSortChange).toHaveBeenCalledWith('blocked')
  })
})
