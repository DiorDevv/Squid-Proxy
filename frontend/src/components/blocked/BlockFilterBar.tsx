import { useState } from 'react'
import { BookmarkPlus, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  BUILT_IN_PRESETS,
  EMPTY_FILTERS,
  splitTerms,
  useBlockPresetsStore,
  type BlockFilterValues,
  type BlockPreset,
} from '@/lib/block-filters'
import { useTranslation, type TranslationKey } from '@/i18n'

const ALL_PROXIES = '__all__'
type TextField = 'domains' | 'clients' | 'users'

const FIELDS: { name: TextField; labelKey: TranslationKey; placeholderKey: TranslationKey; width: string }[] = [
  { name: 'domains', labelKey: 'blocked.filters.domains', placeholderKey: 'blocked.filters.domainsHint', width: 'w-64' },
  { name: 'clients', labelKey: 'blocked.filters.clients', placeholderKey: 'blocked.filters.clientsHint', width: 'w-52' },
  { name: 'users', labelKey: 'blocked.filters.users', placeholderKey: 'blocked.filters.usersHint', width: 'w-36' },
]

/** A text filter that applies on Enter / blur, not on every keystroke --
 * each change re-queries the aggregates. Re-syncs when the applied value
 * changes from outside (a chip removed, a preset, a drill-down). */
function TermInput({
  value,
  onCommit,
  label,
  placeholder,
  className,
}: {
  value: string
  onCommit: (value: string) => void
  label: string
  placeholder: string
  className: string
}) {
  const [draft, setDraft] = useState(value)
  const [applied, setApplied] = useState(value)
  if (value !== applied) {
    setApplied(value)
    setDraft(value)
  }
  const commit = () => {
    if (draft.trim() !== value.trim()) onCommit(draft)
  }
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase text-muted-foreground">{label}</span>
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') setDraft(value)
        }}
        placeholder={placeholder}
        aria-label={label}
        className={`font-data h-8 text-xs ${className}`}
      />
    </label>
  )
}

function PresetsMenu({
  filters,
  onApply,
}: {
  filters: BlockFilterValues
  onApply: (filters: BlockFilterValues) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const saved = useBlockPresetsStore((s) => s.items)
  const save = useBlockPresetsStore((s) => s.save)
  const remove = useBlockPresetsStore((s) => s.remove)
  const hasFilters = Object.values(filters).some((v) => v.trim())

  const presetLabel = (preset: BlockPreset) => (preset.builtIn ? t(preset.name as TranslationKey) : preset.name)
  const apply = (preset: BlockPreset) => {
    onApply(preset.filters)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          <BookmarkPlus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('blocked.presets.title')}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-80 flex-col gap-3">
        <ul className="flex flex-col gap-1">
          {[...BUILT_IN_PRESETS, ...saved].map((preset) => (
            <li key={preset.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => apply(preset)}
                className="flex min-w-0 flex-1 flex-col items-start rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary/60"
              >
                <span className="truncate text-sm text-foreground">{presetLabel(preset)}</span>
                <span className="font-data w-full truncate text-[11px] text-muted-foreground">
                  {[preset.filters.domains, preset.filters.clients, preset.filters.users, preset.filters.proxy]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </button>
              {!preset.builtIn && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t('savedFilters.remove')}
                  onClick={() => remove(preset.id)}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              )}
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-1.5 border-t border-border pt-3">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('blocked.presets.namePlaceholder')}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && name.trim() && hasFilters) {
                save(name.trim(), filters)
                setName('')
              }
            }}
          />
          <Button
            size="icon-sm"
            disabled={!name.trim() || !hasFilters}
            aria-label={t('blocked.presets.save')}
            onClick={() => {
              save(name.trim(), filters)
              setName('')
            }}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">{t('blocked.presets.saveHint')}</p>
      </PopoverContent>
    </Popover>
  )
}

/** The Blocked page's shared filters -- identical on the Requests and the
 * Analysis view, with every applied term shown as a removable chip. */
export function BlockFilterBar({
  filters,
  proxies,
  onChange,
}: {
  filters: BlockFilterValues
  proxies: string[]
  onChange: (patch: Partial<BlockFilterValues>) => void
}) {
  const { t } = useTranslation()
  const chips = FIELDS.flatMap((field) =>
    splitTerms(filters[field.name]).map((term) => ({ field: field.name, labelKey: field.labelKey, term })),
  )
  // keep a picked proxy selectable even when the range no longer has it
  const proxyOptions = filters.proxy && !proxies.includes(filters.proxy) ? [filters.proxy, ...proxies] : proxies

  const removeTerm = (field: TextField, term: string) =>
    onChange({ [field]: splitTerms(filters[field]).filter((x) => x !== term).join(' ') })

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        {FIELDS.map((field) => (
          <TermInput
            key={field.name}
            value={filters[field.name]}
            onCommit={(value) => onChange({ [field.name]: value })}
            label={t(field.labelKey)}
            placeholder={t(field.placeholderKey)}
            className={field.width}
          />
        ))}
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase text-muted-foreground">{t('blocked.group.proxy')}</span>
          <Select
            value={filters.proxy || ALL_PROXIES}
            onValueChange={(v) => onChange({ proxy: v === ALL_PROXIES ? '' : v })}
          >
            <SelectTrigger size="sm" className="h-8 w-40" aria-label={t('blocked.group.proxy')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PROXIES}>{t('blocked.filters.allProxies')}</SelectItem>
              {proxyOptions.map((proxy) => (
                <SelectItem key={proxy} value={proxy}>
                  {proxy}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <PresetsMenu filters={filters} onApply={(next) => onChange(next)} />
      </div>
      {(chips.length > 0 || filters.proxy) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {chips.map((chip) => (
            <span
              key={`${chip.field}:${chip.term}`}
              className="font-data inline-flex items-center gap-1 rounded-full border border-border bg-secondary/50 py-0.5 pl-2 pr-1 text-xs text-foreground"
            >
              <span className="text-muted-foreground">{t(chip.labelKey)}:</span>
              {chip.term}
              <button
                type="button"
                onClick={() => removeTerm(chip.field, chip.term)}
                aria-label={t('blocked.filters.removeTerm', { term: chip.term })}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
          {filters.proxy && (
            <span className="font-data inline-flex items-center gap-1 rounded-full border border-border bg-secondary/50 py-0.5 pl-2 pr-1 text-xs text-foreground">
              <span className="text-muted-foreground">{t('blocked.group.proxy')}:</span>
              {filters.proxy}
              <button
                type="button"
                onClick={() => onChange({ proxy: '' })}
                aria-label={t('blocked.filters.removeTerm', { term: filters.proxy })}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          )}
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => onChange(EMPTY_FILTERS)}>
            {t('blocked.filters.clear')}
          </Button>
        </div>
      )}
    </div>
  )
}
