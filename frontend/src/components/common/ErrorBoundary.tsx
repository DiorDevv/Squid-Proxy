import { Component, type ErrorInfo, type ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { translate, useLocaleStore } from '@/i18n'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

/** Top-level catch-all wrapping <App/> in main.tsx -- without this, any
 * single component throwing during render unmounts the entire React tree
 * with no fallback UI (a silent whitescreen, confirmed nothing like this
 * existed anywhere in the app before). A class component specifically
 * because error boundaries have no hook equivalent as of React 19; reads
 * the locale directly from the store (translate()/useLocaleStore.getState(),
 * not the useTranslation() hook) for the same reason -- hooks aren't
 * available here. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // No error-tracking SDK wired up by default (see SENTRY_DSN) -- this is
    // the fallback so the failure is at least visible somewhere instead of
    // just a blank page.
    console.error('Unhandled error caught by ErrorBoundary:', error, errorInfo)
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children

    const locale = useLocaleStore.getState().locale
    const t = (key: Parameters<typeof translate>[1]) => translate(locale, key)

    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-background text-center">
        <TriangleAlert className="h-6 w-6 text-destructive" aria-hidden="true" />
        <h1 className="text-lg font-semibold text-foreground">{t('errorBoundary.heading')}</h1>
        <p className="max-w-sm text-sm text-muted-foreground">{t('errorBoundary.message')}</p>
        <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
          {t('errorBoundary.reload')}
        </Button>
      </div>
    )
  }
}
