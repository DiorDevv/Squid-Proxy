import { useState } from 'react'
import { Bookmark, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { RANGE_OPTIONS } from '@/lib/constants'
import { useFiltersStore } from '@/lib/filters-store'
import { useSavedFiltersStore, type SavedFilter } from '@/lib/saved-filters-store'
import { useBranches } from '@/hooks/useBranches'
import { useTranslation } from '@/i18n'

/** Applies (or names, for saving) a range+branch combination the same way
 * across every page that renders this -- one label format so a saved
 * filter reads identically regardless of which page it was created or
 * applied from. */
function useFilterLabel() {
  const branches = useBranches()
  return (filter: Pick<SavedFilter, 'mode' | 'range' | 'branch'>) => {
    const rangePart =
      filter.mode === 'custom'
        ? '…' // a custom absolute window has no short label worth computing here
        : (RANGE_OPTIONS.find((option) => option.value === filter.range)?.label ?? filter.range)
    const branchPart = filter.branch
      ? (branches.data?.items.find((item) => item.slug === filter.branch)?.label ?? filter.branch)
      : null
    return branchPart ? `${rangePart} · ${branchPart}` : rangePart
  }
}

/** Save/apply a named range+branch combination -- the one filter shared
 * across Dashboard/Domains/Clients/Blocked (see lib/filters-store.ts), so a
 * preset saved on one of those pages applies cleanly on any of the others.
 * Sits next to BranchSelector/RangeSelector on each of those pages. */
export function SavedFiltersMenu() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [draftName, setDraftName] = useState('')

  const { mode, range, customFrom, customTo, branch, setRange, setCustomRange, setBranch } = useFiltersStore()
  const savedItems = useSavedFiltersStore((state) => state.items)
  const save = useSavedFiltersStore((state) => state.save)
  const remove = useSavedFiltersStore((state) => state.remove)
  const label = useFilterLabel()

  function handleApply(filter: SavedFilter) {
    if (filter.mode === 'custom' && filter.customFrom && filter.customTo) {
      setCustomRange(filter.customFrom, filter.customTo)
    } else {
      setRange(filter.range)
    }
    setBranch(filter.branch)
    setOpen(false)
  }

  function handleSave() {
    const name = draftName.trim()
    if (!name) return
    save({ name, mode, range, customFrom, customTo, branch })
    setDraftName('')
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon-sm" aria-label={t('savedFilters.title')}>
          <Bookmark className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="flex w-72 flex-col gap-3">
        <h2 className="text-sm font-semibold text-foreground">{t('savedFilters.title')}</h2>

        {savedItems.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('savedFilters.empty')}</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {savedItems.map((item) => (
              <li key={item.id} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => handleApply(item)}
                  className="flex min-w-0 flex-1 flex-col items-start rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary/60"
                >
                  <span className="truncate text-sm text-foreground">{item.name}</span>
                  <span className="font-data truncate text-[11px] text-muted-foreground">{label(item)}</span>
                </button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t('savedFilters.remove')}
                  onClick={() => remove(item.id)}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-1.5 border-t border-border pt-3">
          <Input
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            placeholder={t('savedFilters.namePlaceholder')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave()
            }}
          />
          <Button size="icon-sm" onClick={handleSave} disabled={!draftName.trim()} aria-label={t('savedFilters.save')}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">{t('savedFilters.saveHint')}</p>
      </PopoverContent>
    </Popover>
  )
}
