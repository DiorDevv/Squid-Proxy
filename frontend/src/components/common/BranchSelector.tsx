import { Waypoints } from 'lucide-react'
import { useBranches } from '@/hooks/useBranches'
import { useFiltersStore } from '@/lib/filters-store'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from '@/i18n'

const ALL_BRANCHES = 'all'

/** Filters every range-based query down to one configured branch/site (see
 * backend Settings.effective_log_sources) -- mirrors DomainsPage's category
 * Select (an open-ended list, not a fixed few options like RangeSelector's
 * segmented pills). Renders nothing for a single-branch deployment (the
 * common case): a dropdown with only "All branches" and one branch is pure
 * noise. */
export function BranchSelector() {
  const { t } = useTranslation()
  const branches = useBranches()
  const branch = useFiltersStore((state) => state.branch)
  const setBranch = useFiltersStore((state) => state.setBranch)

  const items = branches.data?.items ?? []
  if (items.length <= 1) return null

  return (
    <Select value={branch ?? ALL_BRANCHES} onValueChange={(value) => setBranch(value === ALL_BRANCHES ? null : value)}>
      <SelectTrigger size="sm" className="w-40" aria-label={t('branch.filter')}>
        <Waypoints className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_BRANCHES}>{t('branch.all')}</SelectItem>
        {items.map((item) => (
          <SelectItem key={item.slug} value={item.slug}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
