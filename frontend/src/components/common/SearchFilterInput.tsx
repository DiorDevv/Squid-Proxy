import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'

interface SearchFilterInputProps {
  value: string
  onChange: (value: string) => void
  placeholder: string
  ariaLabel: string
  className?: string
}

/** The IP/domain/user filter box used on Clients and Blocked -- factored out
 * once so both share the same focus/clear micro-interactions instead of
 * drifting apart over time. */
export function SearchFilterInput({ value, onChange, placeholder, ariaLabel, className }: SearchFilterInputProps) {
  const { t } = useTranslation()

  return (
    <div className={cn('group relative w-56', className)}>
      <Search
        className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground transition-colors duration-150 group-focus-within:text-primary"
        aria-hidden="true"
      />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-8 pr-8 pl-8 text-xs"
        aria-label={ariaLabel}
      />
      {value && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1/2 right-1 h-6 w-6 -translate-y-1/2 animate-in zoom-in-75 duration-150"
          onClick={() => onChange('')}
          aria-label={t('common.clearFilter')}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  )
}
