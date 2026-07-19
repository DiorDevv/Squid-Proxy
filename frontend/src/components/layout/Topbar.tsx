import { useLocation } from 'react-router-dom'
import { ConnectionStatus } from '@/components/layout/ConnectionStatus'
import { MobileNav } from '@/components/layout/MobileNav'
import { useTranslation, type TranslationKey } from '@/i18n'

/** Longest/most-specific patterns first so a detail route (e.g.
 * /clients/10.0.0.1) doesn't get shadowed by its list-page prefix. */
const PAGE_TITLE_KEYS: { pattern: RegExp; titleKey: TranslationKey }[] = [
  { pattern: /^\/clients\/[^/]+$/, titleKey: 'topbar.title.clientDetail' },
  { pattern: /^\/clients$/, titleKey: 'topbar.title.clients' },
  { pattern: /^\/blocked$/, titleKey: 'topbar.title.blocked' },
  { pattern: /^\/domains$/, titleKey: 'topbar.title.domains' },
  { pattern: /^\/settings$/, titleKey: 'topbar.title.settings' },
  { pattern: /^\/$/, titleKey: 'topbar.title.dashboard' },
]

function usePageTitleKey(pathname: string): TranslationKey {
  return PAGE_TITLE_KEYS.find(({ pattern }) => pattern.test(pathname))?.titleKey ?? 'topbar.title.default'
}

export function Topbar() {
  const { t } = useTranslation()
  const location = useLocation()
  const pageTitle = t(usePageTitleKey(location.pathname))

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border bg-background/85 px-4 backdrop-blur-md supports-backdrop-filter:bg-background/70">
      <div className="flex min-w-0 items-center gap-3">
        <MobileNav />
        <h1 className="truncate text-sm font-semibold text-foreground">{pageTitle}</h1>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <ConnectionStatus />
      </div>
    </header>
  )
}
