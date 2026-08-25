import { act, renderHook, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTelegramLinkFlow } from '@/hooks/useTelegramLink'
import type { TelegramLinkCodeOut } from '@/types/api'

const SAMPLE_CODE: TelegramLinkCodeOut = { code: '123456', expires_at: '2026-01-01T00:10:00Z' }

describe('useTelegramLinkFlow', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('starts closed with no code', () => {
    const { result } = renderHook(() => useTelegramLinkFlow(() => Promise.resolve(SAMPLE_CODE)))
    expect(result.current.open).toBe(false)
    expect(result.current.code).toBeNull()
  })

  it('connect() only opens the dialog once a code has actually been created', async () => {
    const { result } = renderHook(() => useTelegramLinkFlow(() => Promise.resolve(SAMPLE_CODE)))

    act(() => {
      result.current.connect()
    })

    await waitFor(() => expect(result.current.open).toBe(true))
    expect(result.current.code).toEqual(SAMPLE_CODE)
  })

  it('connect() toasts an error and never opens when code creation fails', async () => {
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => '')
    const { result } = renderHook(() => useTelegramLinkFlow(() => Promise.reject(new Error('boom'))))

    act(() => {
      result.current.connect()
    })

    await waitFor(() => expect(toastSpy).toHaveBeenCalled())
    expect(result.current.open).toBe(false)
    expect(result.current.code).toBeNull()
  })

  it('requestNewCode() replaces the code without touching open', async () => {
    const secondCode: TelegramLinkCodeOut = { code: '654321', expires_at: '2026-01-01T00:20:00Z' }
    const createCode = vi.fn().mockResolvedValueOnce(SAMPLE_CODE).mockResolvedValueOnce(secondCode)
    const { result } = renderHook(() => useTelegramLinkFlow(createCode))

    act(() => {
      result.current.connect()
    })
    await waitFor(() => expect(result.current.code).toEqual(SAMPLE_CODE))

    act(() => {
      result.current.requestNewCode()
    })
    await waitFor(() => expect(result.current.code).toEqual(secondCode))
    expect(result.current.open).toBe(true)
  })

  it('handleOpenChange(false) closes and clears the code, so a later connect() starts fresh', async () => {
    const { result } = renderHook(() => useTelegramLinkFlow(() => Promise.resolve(SAMPLE_CODE)))
    act(() => {
      result.current.connect()
    })
    await waitFor(() => expect(result.current.open).toBe(true))

    act(() => {
      result.current.handleOpenChange(false)
    })

    expect(result.current.open).toBe(false)
    expect(result.current.code).toBeNull()
  })
})
