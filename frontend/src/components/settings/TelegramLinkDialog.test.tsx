import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UseQueryResult } from '@tanstack/react-query'
import { TelegramLinkDialog } from '@/components/settings/TelegramLinkDialog'
import type { TelegramLinkCodeOut, TelegramLinkStatusOut } from '@/types/api'

const SAMPLE_CODE: TelegramLinkCodeOut = {
  code: '123456',
  expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
}

function fakeStatus(data: Partial<TelegramLinkStatusOut> | undefined): UseQueryResult<TelegramLinkStatusOut> {
  return { data } as UseQueryResult<TelegramLinkStatusOut>
}

describe('TelegramLinkDialog', () => {
  const onOpenChange = vi.fn()
  const onRequestNewCode = vi.fn()
  const onLinked = vi.fn()

  beforeEach(() => {
    onOpenChange.mockReset()
    onRequestNewCode.mockReset()
    onLinked.mockReset()
  })

  it('shows a loading placeholder while no code has been created yet', () => {
    render(
      <TelegramLinkDialog
        open
        onOpenChange={onOpenChange}
        title="Connect Telegram"
        instructions="Send this code to the bot."
        code={null}
        onRequestNewCode={onRequestNewCode}
        useStatus={() => fakeStatus(undefined)}
        onLinked={onLinked}
      />,
    )

    expect(screen.queryByText('123456')).not.toBeInTheDocument()
  })

  it('shows the code and a countdown once one has been created', () => {
    render(
      <TelegramLinkDialog
        open
        onOpenChange={onOpenChange}
        title="Connect Telegram"
        instructions="Send this code to the bot."
        code={SAMPLE_CODE}
        onRequestNewCode={onRequestNewCode}
        useStatus={() => fakeStatus({ consumed: false, expired: false, chat_id: null })}
        onLinked={onLinked}
      />,
    )

    expect(screen.getByText('123456')).toBeInTheDocument()
  })

  it('closes, toasts, and invokes onLinked once the status reports consumed', () => {
    render(
      <TelegramLinkDialog
        open
        onOpenChange={onOpenChange}
        title="Connect Telegram"
        instructions="Send this code to the bot."
        code={SAMPLE_CODE}
        onRequestNewCode={onRequestNewCode}
        useStatus={() => fakeStatus({ consumed: true, expired: false, chat_id: '999' })}
        onLinked={onLinked}
      />,
    )

    expect(onLinked).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
