import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'

function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('boom')
  return <div>panel content</div>
}

/** A plain mutable flag (not React state) so it can be flipped *outside*
 * the tree PanelErrorBoundary discards on catch, then observed fresh the
 * next time RecoverableBomb itself re-renders -- simulating "the underlying
 * cause got fixed" between one render attempt and the next. */
const recoverableState = { shouldThrow: true }

function RecoverableBomb() {
  return <Bomb shouldThrow={recoverableState.shouldThrow} />
}

describe('PanelErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    render(
      <PanelErrorBoundary>
        <div>panel content</div>
      </PanelErrorBoundary>,
    )
    expect(screen.getByText('panel content')).toBeInTheDocument()
  })

  it('renders the compact fallback (not the full-page one) when a child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <PanelErrorBoundary>
        <Bomb shouldThrow />
      </PanelErrorBoundary>,
    )

    expect(screen.getByText(/couldn't be displayed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    // The full-page ErrorBoundary's heading/reload text must not appear --
    // proves this is genuinely the compact variant, not a shared fallback.
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()

    vi.restoreAllMocks()
  })

  it('includes the panel label in the fallback message when given', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <PanelErrorBoundary panelLabel="Alert settings">
        <Bomb shouldThrow />
      </PanelErrorBoundary>,
    )

    expect(screen.getByText(/Alert settings/)).toBeInTheDocument()

    vi.restoreAllMocks()
  })

  it('logs the caught error to the console', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <PanelErrorBoundary>
        <Bomb shouldThrow />
      </PanelErrorBoundary>,
    )

    expect(consoleError).toHaveBeenCalledWith(
      'Unhandled error caught by PanelErrorBoundary:',
      expect.any(Error),
      expect.anything(),
    )

    consoleError.mockRestore()
  })

  it('recovers without a full page reload when Retry is clicked after the cause is fixed', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const reloadSpy = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadSpy },
      writable: true,
    })
    const user = userEvent.setup()
    recoverableState.shouldThrow = true

    render(
      <PanelErrorBoundary>
        <RecoverableBomb />
      </PanelErrorBoundary>,
    )

    expect(screen.getByText(/couldn't be displayed/i)).toBeInTheDocument()

    recoverableState.shouldThrow = false
    await user.click(screen.getByRole('button', { name: /retry/i }))

    expect(screen.getByText('panel content')).toBeInTheDocument()
    expect(reloadSpy).not.toHaveBeenCalled()

    vi.restoreAllMocks()
  })
})
