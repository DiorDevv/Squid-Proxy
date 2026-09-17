import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/format'
import {
  isWatchlistConflict,
  useCreateWatchlistEntry,
  useDeleteWatchlistEntry,
  useSetWatchlistActive,
  useWatchlist,
} from '@/hooks/useWatchlist'
import { useBranches } from '@/hooks/useBranches'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { WatchlistTargetType } from '@/types/api'

const TYPE_LABEL_KEYS: Record<WatchlistTargetType, TranslationKey> = {
  client_ip: 'watchlist.typeClientIp',
  domain: 'watchlist.typeDomain',
  user: 'watchlist.typeUser',
}

export function WatchlistPanel() {
  const { t } = useTranslation()
  const query = useWatchlist()
  const create = useCreateWatchlistEntry()
  const setActive = useSetWatchlistActive()
  const remove = useDeleteWatchlistEntry()
  const branches = useBranches()

  const [type, setType] = useState<WatchlistTargetType>('client_ip')
  const [value, setValue] = useState('')
  const [note, setNote] = useState('')
  const [branch, setBranch] = useState('')
  const [error, setError] = useState<string | null>(null)

  const branchItems = branches.data?.items ?? []

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    setError(null)
    create.mutate(
      { target_type: type, value: value.trim(), note: note.trim() || null, branch },
      {
        onSuccess: () => {
          setValue('')
          setNote('')
        },
        onError: (err) =>
          setError(isWatchlistConflict(err) ? t('watchlist.conflict') : t('common.errorDefault')),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">{t('watchlist.intro')}</p>

      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('watchlist.type')}
          <Select value={type} onValueChange={(v) => setType(v as WatchlistTargetType)}>
            <SelectTrigger size="sm" className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(['client_ip', 'domain', 'user'] as const).map((v) => (
                <SelectItem key={v} value={v}>
                  {t(TYPE_LABEL_KEYS[v])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('watchlist.value')}
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t('watchlist.valuePlaceholder')}
            className="w-48"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('watchlist.note')}
          <Input value={note} onChange={(e) => setNote(e.target.value)} className="w-48" />
        </label>
        {branchItems.length > 1 && (
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            {t('branch.filter')}
            <Select value={branch || 'any'} onValueChange={(v) => setBranch(v === 'any' ? '' : v)}>
              <SelectTrigger size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">{t('branch.all')}</SelectItem>
                {branchItems.map((b) => (
                  <SelectItem key={b.slug} value={b.slug}>
                    {b.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        )}
        <Button type="submit" size="sm" disabled={create.isPending || !value.trim()}>
          {t('watchlist.add')}
        </Button>
      </form>
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}

      {query.isError ? (
        <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
      ) : query.isLoading ? (
        <div className="h-32 animate-pulse rounded bg-muted" />
      ) : (query.data?.length ?? 0) === 0 ? (
        <EmptyState message={t('watchlist.empty')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-2 pr-3 font-medium">{t('watchlist.colTarget')}</th>
                <th className="py-2 pr-3 font-medium">{t('branch.filter')}</th>
                <th className="py-2 pr-3 font-medium">{t('watchlist.colNote')}</th>
                <th className="py-2 pr-3 font-medium">{t('watchlist.colLastSeen')}</th>
                <th className="py-2 pr-3 font-medium">{t('watchlist.colLastAlert')}</th>
                <th className="py-2 pr-3 font-medium">{t('watchlist.colActive')}</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {query.data?.map((entry) => (
                <tr key={entry.id} className={cn('border-b border-border/50', !entry.active && 'opacity-50')}>
                  <td className="py-2 pr-3">
                    <span className="font-data font-medium text-foreground">{entry.value}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {t(TYPE_LABEL_KEYS[entry.target_type])}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {entry.branch || t('branch.all')}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">{entry.note ?? '—'}</td>
                  <td className="py-2 pr-3 font-data text-xs text-muted-foreground">
                    {formatRelativeTime(entry.last_seen_at)}
                  </td>
                  <td className="py-2 pr-3 font-data text-xs text-muted-foreground">
                    {formatRelativeTime(entry.last_alerted_at)}
                  </td>
                  <td className="py-2 pr-3">
                    <button
                      type="button"
                      onClick={() => setActive.mutate({ id: entry.id, active: !entry.active })}
                      className={cn(
                        'rounded px-1.5 py-0.5 text-xs font-medium',
                        entry.active ? 'bg-success/15 text-success' : 'bg-muted text-muted-foreground',
                      )}
                    >
                      {entry.active ? t('watchlist.on') : t('watchlist.off')}
                    </button>
                  </td>
                  <td className="py-2 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove.mutate(entry.id)}
                      aria-label={t('watchlist.delete')}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
