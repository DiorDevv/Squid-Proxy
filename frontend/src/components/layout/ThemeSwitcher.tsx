import { cn } from '@/lib/utils'
import { BRAND_THEMES, useThemeStore, type BrandTheme } from '@/lib/theme-store'
import { useTranslation } from '@/i18n'
import type { TranslationKey } from '@/i18n'

const SWATCHES: Record<BrandTheme, string> = {
  amber: '#f5a524',
  azure: '#3b82f6',
  violet: '#a855f7',
}

const LABEL_KEYS: Record<BrandTheme, TranslationKey> = {
  amber: 'account.themeAmber',
  azure: 'account.themeAzure',
  violet: 'account.themeViolet',
}

export function ThemeSwitcher() {
  const { t } = useTranslation()
  const brand = useThemeStore((state) => state.brand)
  const setBrand = useThemeStore((state) => state.setBrand)

  return (
    <div className="flex items-center gap-2" role="group" aria-label={t('account.theme')}>
      {BRAND_THEMES.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => setBrand(option)}
          aria-pressed={brand === option}
          aria-label={t(LABEL_KEYS[option])}
          title={t(LABEL_KEYS[option])}
          className={cn(
            'relative h-5 w-5 rounded-full border-2 bg-clip-padding shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),inset_0_-1px_2px_rgba(0,0,0,0.3)] transition-all duration-200 ease-out hover:scale-125 active:scale-95',
            brand === option ? 'scale-110 border-foreground' : 'border-transparent opacity-60 hover:opacity-100',
          )}
          style={{
            backgroundColor: SWATCHES[option],
            boxShadow:
              brand === option
                ? `inset 0 1px 1px rgba(255,255,255,0.4), inset 0 -1px 2px rgba(0,0,0,0.3), 0 0 10px -2px ${SWATCHES[option]}`
                : undefined,
          }}
        />
      ))}
    </div>
  )
}
