import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface NotificationsState {
  /** ISO timestamp of the newest anomaly the admin has actually opened the
   * bell dropdown to see -- everything from GET /api/insights/recent newer
   * than this counts as "unread" for the badge. `null` means never opened
   * (so on a first-ever visit, every anomaly the backend already has shows
   * as unread rather than the badge silently starting empty). */
  lastSeenAt: string | null
  markAllSeen: (at: string) => void
}

/** Persisted client-side only -- there's no per-admin "read" state on the
 * backend (AnomalyEvent has no such column), matching this app's existing
 * pattern of keeping purely-cosmetic UI state (theme, locale) out of the
 * database. The tradeoff: "unread" is per-browser, not per-account -- an
 * admin who reads the same anomaly on two different computers sees it
 * unread on both, which is the same shape as a browser's own notification
 * permission state, not something users generally find surprising. */
export const useNotificationsStore = create<NotificationsState>()(
  persist(
    (set) => ({
      lastSeenAt: null,
      markAllSeen: (at) => set({ lastSeenAt: at }),
    }),
    { name: 'squid-watch-notifications-seen' },
  ),
)
