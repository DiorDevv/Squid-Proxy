import type { TranslationKey } from '@/i18n'
import type { Permission, Role } from '@/types/auth'

interface SettingsNavItem {
  to: string
  labelKey: TranslationKey
  /** Shown to an admin/super admin regardless of `permissions`. */
  admin: boolean
  /** Any-of: shown to anyone holding one of these. Empty = admin only. */
  permissions: Permission[]
  /** Only for an unrestricted admin (the global super-admin Telegram chat). */
  unrestrictedOnly?: boolean
}

// Same gates as the routes in App.tsx -- the backend enforces each one again.
export const SETTINGS_NAV_ITEMS: SettingsNavItem[] = [
  { to: 'general', labelKey: 'settings.nav.general', admin: true, permissions: [] },
  { to: 'users', labelKey: 'settings.nav.users', admin: true, permissions: [] },
  { to: 'audit', labelKey: 'settings.nav.audit', admin: false, permissions: ['audit'] },
  { to: 'policy', labelKey: 'settings.nav.policy', admin: false, permissions: ['audit'] },
  {
    to: 'system-health',
    labelKey: 'settings.nav.systemHealth',
    admin: false,
    permissions: ['audit'],
  },
  {
    to: 'categories',
    labelKey: 'settings.nav.categories',
    admin: false,
    permissions: ['categories', 'alerts', 'reports'],
  },
  { to: 'watchlist', labelKey: 'settings.nav.watchlist', admin: false, permissions: ['watchlist'] },
  { to: 'export', labelKey: 'settings.nav.export', admin: false, permissions: ['raw_export'] },
  { to: 'retention', labelKey: 'settings.nav.retention', admin: true, permissions: [] },
  {
    to: 'telegram',
    labelKey: 'settings.nav.telegram',
    admin: true,
    permissions: [],
    unrestrictedOnly: true,
  },
]

export function visibleSettingsItems(
  role: Role | null,
  permissions: readonly Permission[],
  unrestricted: boolean,
): SettingsNavItem[] {
  const isAdmin = role === 'superadmin' || role === 'admin'
  return SETTINGS_NAV_ITEMS.filter((item) => {
    if (item.unrestrictedOnly) return isAdmin && unrestricted
    if (item.admin && isAdmin) return true
    return item.permissions.some((p) => permissions.includes(p))
  })
}

export function firstSettingsPage(role: Role | null, permissions: readonly Permission[]): string {
  return visibleSettingsItems(role, permissions, false)[0]?.to ?? '/'
}
