import { cn } from '@/lib/utils'
import { useTranslation, type TranslationKey } from '@/i18n'

interface ToggleProps<T extends string> {
  value: T
  options: { value: T; labelKey: TranslationKey }[]
  onChange: (value: T) => void
}

/** Small segmented button group used across the analytics views for
 * granularity (hourly/daily), metric (data/requests), scope (all/blocked),
 * etc. */
export function Toggle<T extends string>({ value, options, onChange }: ToggleProps<T>) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={cn(
            'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
            value === option.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t(option.labelKey)}
        </button>
      ))}
    </div>
  )
}
