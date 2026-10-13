import { create } from 'zustand'

/**
 * Sensitive user-management calls answer 403 "reauth_required" unless the
 * password was entered on this session within the last few minutes (see
 * backend api/deps.require_reauth). apiFetch then calls requestReauth(),
 * which opens <ReauthDialog> and resolves once the user has confirmed
 * their password (true) or cancelled (false); on true apiFetch retries the
 * original call, so no individual caller has to know about re-auth.
 */
interface ReauthState {
  open: boolean
  pending: Promise<boolean> | null
  resolve: ((confirmed: boolean) => void) | null
  settle: (confirmed: boolean) => void
}

export const useReauthStore = create<ReauthState>((set, get) => ({
  open: false,
  pending: null,
  resolve: null,
  settle: (confirmed) => {
    get().resolve?.(confirmed)
    set({ open: false, pending: null, resolve: null })
  },
}))

export function requestReauth(): Promise<boolean> {
  const state = useReauthStore.getState()
  // Several calls hitting the requirement at once share one prompt.
  if (state.pending) return state.pending
  let resolve: (confirmed: boolean) => void = () => {}
  const pending = new Promise<boolean>((r) => {
    resolve = r
  })
  useReauthStore.setState({ open: true, pending, resolve })
  return pending
}
