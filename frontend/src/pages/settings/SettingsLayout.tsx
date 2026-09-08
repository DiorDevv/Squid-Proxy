import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import { useTranslation, type TranslationKey } from '@/i18n'

// `adminOnly` items are hidden from an `auditor`, who only gets the audit
// sub-page under Settings (backend enforces the rest regardless).
const SETTINGS_NAV_ITEMS: { to: string; labelKey: TranslationKey; adminOnly: boolean }[] = [
  { to: 'general', labelKey: 'settings.nav.general', adminOnly: true },
  { to: 'users', labelKey: 'settings.nav.users', adminOnly: true },
  { to: 'audit', labelKey: 'settings.nav.audit', adminOnly: false },
  { to: 'policy', labelKey: 'settings.nav.policy', adminOnly: false },
  { to: 'system-health', labelKey: 'settings.nav.systemHealth', adminOnly: false },
  { to: 'categories', labelKey: 'settings.nav.categories', adminOnly: true },
  { to: 'watchlist', labelKey: 'settings.nav.watchlist', adminOnly: true },
  { to: 'export', labelKey: 'settings.nav.export', adminOnly: true },
]

// Only an unrestricted admin (branch === null) may link the global
// super-admin Telegram chat -- see SettingsTelegramPage. Kept out of
// SETTINGS_NAV_ITEMS (rather than filtered inline below) so a
// branch-scoped admin's nav is otherwise identical to today's.
const SUPER_ADMIN_NAV_ITEM: { to: string; labelKey: TranslationKey } = {
  to: 'telegram',
  labelKey: 'settings.nav.telegram',
}

/** Splits what used to be one long, nine-panel scroll into four focused
 * sub-pages (own URL each, e.g. /settings/export) behind this shared side
 * nav -- see SettingsGeneralPage/UsersPage/CategoriesPage/ExportPage. */
export default function SettingsLayout() {
  const { t } = useTranslation()
  const { branch, role } = useAuth()
  const visible = SETTINGS_NAV_ITEMS.filter((item) => role === 'admin' || !item.adminOnly)
  const navItems =
    role === 'admin' && branch === null ? [...visible, SUPER_ADMIN_NAV_ITEM] : visible

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
      <nav className="flex shrink-0 flex-row gap-1 overflow-x-auto sm:w-48 sm:flex-col sm:overflow-visible">
        {navItems.map(({ to, labelKey }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'shrink-0 rounded-md border-l-2 border-transparent px-3 py-2 text-sm font-medium whitespace-nowrap transition-all duration-150',
                'text-muted-foreground hover:bg-secondary hover:text-foreground',
                isActive &&
                  'border-l-primary bg-gradient-to-r from-primary/15 to-transparent text-primary hover:text-primary',
              )
            }
          >
            {t(labelKey)}
          </NavLink>
        ))}
      </nav>
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
