import { useLayoutEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { LOCALES, useTranslation, type Locale } from '@/i18n'

const LOCALE_LABELS: Record<Locale, string> = {
  uz: "O'Z",
  ru: 'РУ',
  en: 'EN',
}

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useTranslation()
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null)

  useLayoutEffect(() => {
    const activeButton = buttonRefs.current[locale]
    if (activeButton) {
      setIndicator({ left: activeButton.offsetLeft, width: activeButton.offsetWidth })
    }
  }, [locale])

  return (
    <div
      className="relative inline-flex items-center rounded-md border border-border bg-secondary/50 p-0.5"
      role="group"
      aria-label={t('account.language')}
    >
      {indicator && (
        <div
          className="pointer-events-none absolute top-0.5 bottom-0.5 rounded-[calc(var(--radius-sm)-2px)] bg-primary transition-[left,width] duration-250 ease-out"
          style={{ left: indicator.left, width: indicator.width }}
          aria-hidden="true"
        />
      )}
      {LOCALES.map((option) => (
        <button
          key={option}
          ref={(el) => {
            buttonRefs.current[option] = el
          }}
          type="button"
          onClick={() => setLocale(option)}
          aria-pressed={locale === option}
          className={cn(
            'font-data relative z-10 rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-200',
            locale === option ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {LOCALE_LABELS[option]}
        </button>
      ))}
    </div>
  )
}
