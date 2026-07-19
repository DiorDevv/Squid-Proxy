import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ErrorState } from '@/components/common/ErrorState'

describe('ErrorState', () => {
  it('renders the default message when none is given', () => {
    render(<ErrorState />)
    expect(screen.getByText(/could not reach the backend/i)).toBeInTheDocument()
  })

  // Regression coverage for the "surface real API error messages" fix --
  // callers now pass query.error?.message instead of relying on the
  // generic fallback everywhere.
  it('renders a custom message when provided', () => {
    render(<ErrorState message="You do not have permission to view this." />)
    expect(screen.getByText('You do not have permission to view this.')).toBeInTheDocument()
  })

  it('does not render a retry button when onRetry is not given', () => {
    render(<ErrorState />)
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('calls onRetry when the retry button is clicked', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(<ErrorState onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: /retry/i }))

    expect(onRetry).toHaveBeenCalledOnce()
  })
})
