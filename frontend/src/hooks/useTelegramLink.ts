import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, apiFetch } from '@/lib/api-client'
import { useTranslation } from '@/i18n'
import type { TelegramLinkCodeOut, TelegramLinkStatusOut, TelegramSuperAdminOut } from '@/types/api'

const ALERT_SETTINGS_QUERY_KEY = ['alert-settings']
const SUPER_ADMIN_TELEGRAM_QUERY_KEY = ['telegram-super-admin']
const POLL_INTERVAL_MS = 2_000

/** Issues a fresh 6-digit pairing code for `branch` (see
 * backend/app/api/routes/alert_settings.py:create_telegram_link_code). */
export function useCreateTelegramLinkCode(branch: string) {
  return useMutation({
    mutationFn: () =>
      apiFetch<TelegramLinkCodeOut>('/api/alert-settings/telegram-link', {
        method: 'POST',
        searchParams: { branch },
      }),
  })
}

/** Same as above, but for the global super-admin chat -- only reachable by
 * an unrestricted admin (branch === null), see SettingsTelegramPage. */
export function useCreateSuperAdminTelegramLinkCode() {
  return useMutation({
    mutationFn: () =>
      apiFetch<TelegramLinkCodeOut>('/api/alert-settings/telegram-link/super-admin', { method: 'POST' }),
  })
}

/** Polls a pairing code's redemption status while it's still pending, and
 * stops once it's consumed or expired -- same "poll while active" idiom as
 * useExportJob.ts. `code` is null when no code is currently being shown,
 * which disables the query entirely. `onSettled` callbacks (invalidating
 * the alert-settings/super-admin queries once consumed) are the caller's
 * job, not this hook's. */
export function useTelegramLinkStatus(code: string | null) {
  return useQuery({
    queryKey: ['telegram-link-status', code],
    queryFn: () => apiFetch<TelegramLinkStatusOut>(`/api/alert-settings/telegram-link/${code}/status`),
    enabled: code !== null,
    refetchInterval: (query) => (query.state.data?.consumed || query.state.data?.expired ? false : POLL_INTERVAL_MS),
  })
}

export function useSuperAdminTelegram() {
  return useQuery({
    queryKey: SUPER_ADMIN_TELEGRAM_QUERY_KEY,
    queryFn: () => apiFetch<TelegramSuperAdminOut>('/api/alert-settings/telegram-super-admin'),
  })
}

/** Invalidates whichever query reflects a just-consumed pairing code's
 * target, so the caller's status display refreshes immediately instead of
 * waiting for that query's own next refetch. */
export function useInvalidateTelegramLinkTarget() {
  const queryClient = useQueryClient()
  return {
    invalidateBranch: (branch: string) =>
      queryClient.invalidateQueries({ queryKey: [...ALERT_SETTINGS_QUERY_KEY, branch] }),
    invalidateSuperAdmin: () => queryClient.invalidateQueries({ queryKey: SUPER_ADMIN_TELEGRAM_QUERY_KEY }),
  }
}

/** Owns a pairing code's create/reopen lifecycle so TelegramLinkDialog
 * itself can stay purely presentational (no data-fetching effects of its
 * own -- see that component's docstring for why: an effect that fetches
 * "on open" and one whose local setState calls are reachable from an
 * effect both trip the React Compiler's set-state-in-effect lint rule,
 * which can't tell that constructing the resulting state *here*, in the
 * event handler that also flips `open`, is exactly the escape hatch it's
 * asking for).
 *
 * `connect()` creates a code and only opens the dialog once one exists
 * (never opens on a bare click, before there's anything to show).
 * `requestNewCode()` is for the in-dialog "get a new code" retry after
 * expiry -- same creation call, but doesn't touch `open`. Both surface a
 * creation failure as a toast rather than dialog-internal state, matching
 * this codebase's established save/error-toast convention elsewhere
 * (e.g. AlertSettingsPanel's handleSave). */
export function useTelegramLinkFlow(createCode: () => Promise<TelegramLinkCodeOut>) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState<TelegramLinkCodeOut | null>(null)

  function requestNewCode() {
    createCode()
      .then(setCode)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t('common.errorDefault')))
  }

  function connect() {
    createCode()
      .then((result) => {
        setCode(result)
        setOpen(true)
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t('common.errorDefault')))
  }

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) setCode(null)
  }

  return { open, code, connect, requestNewCode, handleOpenChange }
}
