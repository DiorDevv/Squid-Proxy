import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { en, type TranslationKey } from './locales/en'
import { ru } from './locales/ru'
import { uz } from './locales/uz'

export type Locale = 'uz' | 'ru' | 'en'
export const LOCALES: Locale[] = ['uz', 'ru', 'en']

const dictionaries: Record<Locale, Record<TranslationKey, string>> = { uz, ru, en }

type Vars = Record<string, string | number>

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template
  return template.replace(/\{\{(\w+)\}\}/g, (match, key: string) => (key in vars ? String(vars[key]) : match))
}

/** Looks up `key` in `locale`'s dictionary, falling back to English (and
 * finally the raw key itself) rather than ever rendering a blank string --
 * see locales/en.ts for why a missing key can't happen for uz/ru at all. */
export function translate(locale: Locale, key: TranslationKey, vars?: Vars): string {
  const template = dictionaries[locale][key] ?? dictionaries.en[key] ?? key
  return interpolate(template, vars)
}

interface LocaleState {
  locale: Locale
  setLocale: (locale: Locale) => void
}

function applyLocale(locale: Locale): void {
  document.documentElement.lang = locale
}

/** Persisted UI language (see index.css/theme-store.ts for the analogous
 * color-theme picker). Applied eagerly here and again in
 * onRehydrateStorage so <html lang> is correct as soon as possible. */
export const useLocaleStore = create<LocaleState>()(
  persist(
    (set) => ({
      locale: 'en',
      setLocale: (locale) => {
        applyLocale(locale)
        set({ locale })
      },
    }),
    {
      name: 'squid-watch-locale',
      onRehydrateStorage: () => (state) => {
        if (state) applyLocale(state.locale)
      },
    },
  ),
)

applyLocale(useLocaleStore.getState().locale)

export function useTranslation() {
  const locale = useLocaleStore((state) => state.locale)
  const setLocale = useLocaleStore((state) => state.setLocale)

  function t(key: TranslationKey, vars?: Vars): string {
    return translate(locale, key, vars)
  }

  return { t, locale, setLocale }
}

export type { TranslationKey }
