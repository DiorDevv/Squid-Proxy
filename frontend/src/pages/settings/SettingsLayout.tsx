import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useTranslation, type TranslationKey } from '@/i18n'

const SETTINGS_NAV_ITEMS: { to: string; labelKey: TranslationKey }[] = [
  { to: 'general', labelKey: 'settings.nav.general' },
  { to: 'users', labelKey: 'settings.nav.users' },
  { to: 'categories', labelKey: 'settings.nav.categories' },
  { to: 'export', labelKey: 'settings.nav.export' },
]

/** Splits what used to be one long, nine-panel scroll into four focused
 * sub-pages (own URL each, e.g. /settings/export) behind this shared side
 * nav -- see SettingsGeneralPage/UsersPage/CategoriesPage/ExportPage. */
export default function SettingsLayout() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
      <nav className="flex shrink-0 flex-row gap-1 overflow-x-auto sm:w-48 sm:flex-col sm:overflow-visible">
        {SETTINGS_NAV_ITEMS.map(({ to, labelKey }) => (
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
