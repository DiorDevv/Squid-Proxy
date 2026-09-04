import { NavLink, Outlet } from 'react-router-dom'
import { BranchSelector } from '@/components/common/BranchSelector'
import { RangeSelector } from '@/components/common/RangeSelector'
import { cn } from '@/lib/utils'
import { useTranslation, type TranslationKey } from '@/i18n'

const ANALYTICS_NAV_ITEMS: { to: string; labelKey: TranslationKey }[] = [
  { to: 'overview', labelKey: 'analytics.nav.overview' },
  { to: 'branches', labelKey: 'analytics.nav.branches' },
  { to: 'categories', labelKey: 'analytics.nav.categories' },
  { to: 'heatmap', labelKey: 'analytics.nav.heatmap' },
]

/** Four analytics views behind one shared sub-nav and a single
 * range/branch filter row (all four read the same
 * useRangeSearchParams-backed selection). */
export default function AnalyticsLayout() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <nav className="flex flex-row gap-1 overflow-x-auto">
          {ANALYTICS_NAV_ITEMS.map(({ to, labelKey }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'shrink-0 rounded-md border-b-2 border-transparent px-3 py-2 text-sm font-medium whitespace-nowrap transition-all duration-150',
                  'text-muted-foreground hover:bg-secondary hover:text-foreground',
                  isActive && 'border-b-primary bg-primary/10 text-primary hover:text-primary',
                )
              }
            >
              {t(labelKey)}
            </NavLink>
          ))}
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          <BranchSelector />
          <RangeSelector />
        </div>
      </div>

      <Outlet />
    </div>
  )
}
