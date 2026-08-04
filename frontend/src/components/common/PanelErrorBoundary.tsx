import { Component, type ErrorInfo, type ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { translate, useLocaleStore } from '@/i18n'

interface PanelErrorBoundaryProps {
  children: ReactNode
  /** Identifies which panel broke in the compact fallback -- useful on
   * pages with several independent panels (e.g. Settings' 8), where a
   * generic "this panel couldn't be displayed" wouldn't say which one. */
  panelLabel?: string
}

interface PanelErrorBoundaryState {
  hasError: boolean
}

/** A panel-scoped sibling to ErrorBoundary (main.tsx's app-root boundary):
 * that one is a full-page takeover with a reload button, appropriate for an
 * app-wide crash. A single panel crashing shouldn't take the rest of the
 * page down with it, and doesn't need a full reload to recover -- just
 * resetting local state and re-rendering children is enough, since
 * everything else on the page was fine. Kept as a separate component
 * rather than a `fallback` prop on ErrorBoundary since the two have
 * different reset semantics, not just different markup. */
export class PanelErrorBoundary extends Component<
  PanelErrorBoundaryProps,
  PanelErrorBoundaryState
> {
  state: PanelErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): PanelErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('Unhandled error caught by PanelErrorBoundary:', error, errorInfo)
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false })
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children

    const locale = useLocaleStore.getState().locale
    const t = (key: Parameters<typeof translate>[1], vars?: Parameters<typeof translate>[2]) =>
      translate(locale, key, vars)

    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-destructive/40 bg-destructive/5 p-4 text-center">
        <TriangleAlert className="h-4 w-4 text-destructive" aria-hidden="true" />
        <p className="text-xs text-muted-foreground">
          {this.props.panelLabel
            ? t('panelErrorBoundary.messageWithLabel', { panel: this.props.panelLabel })
            : t('panelErrorBoundary.message')}
        </p>
        <Button variant="outline" size="sm" onClick={this.handleRetry}>
          {t('panelErrorBoundary.retry')}
        </Button>
      </div>
    )
  }
}
