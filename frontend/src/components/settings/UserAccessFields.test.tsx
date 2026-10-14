import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BranchPicker, PermissionPicker } from '@/components/settings/UserAccessFields'
import { isExpired } from '@/lib/permissions'

const BRANCHES = [
  { slug: 'main', label: 'Main' },
  { slug: 'filial', label: 'Filial' },
  { slug: 'server', label: 'Server' },
]

describe('BranchPicker', () => {
  it('adds a second branch in config order', () => {
    const onChange = vi.fn()
    render(
      <BranchPicker
        idPrefix="t"
        value={['filial']}
        onChange={onChange}
        options={BRANCHES}
        allowUnrestricted
      />,
    )
    fireEvent.click(screen.getByLabelText('Main'))
    expect(onChange).toHaveBeenCalledWith(['main', 'filial'])
  })

  it('never leaves the account with no branch', () => {
    const onChange = vi.fn()
    render(
      <BranchPicker
        idPrefix="t"
        value={['main']}
        onChange={onChange}
        options={BRANCHES}
        allowUnrestricted
      />,
    )
    fireEvent.click(screen.getByLabelText('Main'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('hides "all branches" from a branch-limited actor', () => {
    render(
      <BranchPicker
        idPrefix="t"
        value={['main']}
        onChange={() => {}}
        options={BRANCHES}
        allowUnrestricted={false}
      />,
    )
    expect(screen.queryByLabelText(/all branches|barcha filiallar/i)).toBeNull()
  })
})

describe('PermissionPicker', () => {
  it('switches from role defaults to an explicit list starting from those defaults', () => {
    const onChange = vi.fn()
    render(
      <PermissionPicker
        idPrefix="p"
        role="auditor"
        value={null}
        onChange={onChange}
        grantable={['export', 'audit', 'watchlist']}
      />,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: /role default|rol boʻyicha/i }))
    expect(onChange).toHaveBeenCalledWith(['export', 'audit'])
  })

  it('keeps permissions the actor lacks disabled', () => {
    render(
      <PermissionPicker
        idPrefix="p"
        role="viewer"
        value={[]}
        onChange={() => {}}
        grantable={['export']}
      />,
    )
    const checkboxes = screen.getAllByRole('checkbox')
    // [defaults toggle, export, raw_export, ...] -- only export is grantable.
    expect(checkboxes[1]).not.toBeDisabled()
    expect(checkboxes[2]).toBeDisabled()
  })
})

describe('isExpired', () => {
  it('treats a past end date as expired and none as never', () => {
    expect(isExpired(new Date(Date.now() - 1000).toISOString())).toBe(true)
    expect(isExpired(new Date(Date.now() + 60_000).toISOString())).toBe(false)
    expect(isExpired(null)).toBe(false)
  })
})
