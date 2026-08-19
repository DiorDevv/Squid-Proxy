import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Globe, Search, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { EmptyState } from '@/components/common/EmptyState'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useGlobalSearch } from '@/hooks/useGlobalSearch'
import { useTranslation } from '@/i18n'

/** Topbar search reachable from every page -- looks up clients (by IP or
 * user) and domains in parallel (see useGlobalSearch) and jumps straight to
 * the matching detail page, so finding "that one client" no longer means
 * navigating to Clients and typing into its own list filter first. */
export function GlobalSearch() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query, 300)
  const { clients, domains, isLoading, isError } = useGlobalSearch(debouncedQuery)

  const hasQuery = query.trim().length > 0
  const hasResults = clients.length > 0 || domains.length > 0

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) setQuery('')
  }

  // Ctrl/Cmd+K opens this from anywhere -- browsers bind that combo to their
  // own address-bar search, so it's preventDefault'd here rather than left
  // to fall through. Toggles rather than just opening, so the same shortcut
  // also dismisses it without reaching for Escape.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((prev) => {
          const next = !prev
          if (!next) setQuery('')
          return next
        })
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  function goTo(path: string) {
    navigate(path)
    handleOpenChange(false)
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={t('globalSearch.triggerLabel')}>
          <Search className="h-4 w-4" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="border-b border-border p-2">
          <Input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('globalSearch.placeholder')}
            aria-label={t('globalSearch.placeholder')}
            className="h-8 text-xs"
          />
        </div>
        <div className="max-h-96 overflow-y-auto p-2">
          {!hasQuery ? (
            <EmptyState message={t('globalSearch.hint')} />
          ) : isLoading ? (
            <div className="flex flex-col gap-2 p-1">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-9 w-full animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : isError ? (
            <EmptyState message={t('globalSearch.error')} />
          ) : !hasResults ? (
            <EmptyState message={t('globalSearch.noResults', { query: query.trim() })} />
          ) : (
            <div className="flex flex-col gap-3">
              {clients.length > 0 && (
                <div>
                  <h3 className="px-1 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {t('globalSearch.clients')}
                  </h3>
                  <ul className="flex flex-col gap-0.5">
                    {clients.map((client) => (
                      <li key={client.client_ip}>
                        <button
                          type="button"
                          onClick={() => goTo(`/clients/${encodeURIComponent(client.client_ip)}`)}
                          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary/60"
                        >
                          <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="flex min-w-0 flex-col">
                            <span className="font-data truncate text-sm text-foreground">{client.client_ip}</span>
                            {client.user && (
                              <span className="truncate text-[11px] text-muted-foreground">{client.user}</span>
                            )}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {domains.length > 0 && (
                <div>
                  <h3 className="px-1 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    {t('globalSearch.domains')}
                  </h3>
                  <ul className="flex flex-col gap-0.5">
                    {domains.map((domain) => (
                      <li key={domain.domain}>
                        <button
                          type="button"
                          onClick={() => goTo(`/domains/${encodeURIComponent(domain.domain)}`)}
                          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary/60"
                        >
                          <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="truncate text-sm text-foreground">{domain.domain}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
