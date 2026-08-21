import { useMemo, useRef } from 'react'
import { toast } from 'sonner'
import { Download, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTopDomains } from '@/hooks/useTopDomains'
import { useDomainCategories, useImportDomainCategories, useSetDomainCategory } from '@/hooks/useDomainCategories'
import { downloadDomainCategoriesExport } from '@/lib/api-client'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { DomainCategoryLabel } from '@/types/api'

/** Lets an admin tag the domains actually seen in traffic (the last 7 days'
 * top 50, by request volume) with a category -- there's no separate "known
 * domains" registry, so the top-domains list doubles as the candidate set.
 * Each row's dropdown defaults to /api/top-domains' `category` field, which
 * is the auto-inferred guess (category_inference.py) for anything the admin
 * hasn't explicitly overridden yet -- so this list starts pre-filled with
 * sensible defaults instead of everything showing "Uncategorized". */
export function DomainCategoriesPanel() {
  const { t } = useTranslation()
  const topDomains = useTopDomains({ range: '7d' }, 50, false)
  const categories = useDomainCategories()
  const setCategory = useSetDomainCategory()
  const importCategories = useImportDomainCategories()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const overrideByDomain = useMemo(() => {
    const map = new Map<string, DomainCategoryLabel>()
    for (const row of categories.data ?? []) map.set(row.domain, row.category)
    return map
  }, [categories.data])

  function handleChange(domain: string, category: DomainCategoryLabel) {
    setCategory.mutate({ domain, category }, { onError: () => toast.error(t('common.errorDefault')) })
  }

  async function handleExport() {
    try {
      await downloadDomainCategoriesExport()
    } catch {
      toast.error(t('common.errorDefault'))
    }
  }

  function handleImportClick() {
    fileInputRef.current?.click()
  }

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset immediately so picking the exact same file again still fires
    // onChange -- the browser otherwise treats an unchanged file list as
    // nothing having happened.
    event.target.value = ''
    if (!file) return

    importCategories.mutate(file, {
      onSuccess: (result) => {
        if (result.errors.length === 0) {
          toast.success(t('settings.categoriesImportSuccess', { count: result.applied }))
          return
        }
        toast.warning(
          t('settings.categoriesImportPartial', { applied: result.applied, errors: result.errors.length }),
          {
            description: result.errors
              .slice(0, 5)
              .map((e) => `${t('settings.categoriesImportRow', { row: e.row })}: ${e.reason}`)
              .join('\n'),
          },
        )
      },
      onError: () => toast.error(t('common.errorDefault')),
    })
  }

  if (topDomains.isLoading || categories.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  if (topDomains.isError) {
    return <ErrorState message={topDomains.error?.message} onRetry={() => topDomains.refetch()} />
  }

  const domains = topDomains.data?.items ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t('settings.categoriesImportExportHint')}</p>
        <div className="flex shrink-0 gap-1.5">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={handleExport}>
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.categoriesExport')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={handleImportClick}
            disabled={importCategories.isPending}
          >
            <Upload className="h-3.5 w-3.5" aria-hidden="true" />
            {importCategories.isPending ? t('settings.categoriesImporting') : t('settings.categoriesImport')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileSelected}
          />
        </div>
      </div>

      <ul className="scrollbar-thin -mr-1 flex max-h-96 flex-col divide-y divide-border overflow-y-auto pr-1">
        {domains.map((item) => (
          <li key={item.domain} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="font-data min-w-0 flex-1 truncate text-foreground" title={item.domain}>
              {item.domain}
            </span>
            <Select
              value={overrideByDomain.get(item.domain) ?? item.category}
              onValueChange={(value) => handleChange(item.domain, value as DomainCategoryLabel)}
            >
              <SelectTrigger size="sm" className="w-40" aria-label={item.domain}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {t(CATEGORY_LABEL_KEYS[option])}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </li>
        ))}
      </ul>
    </div>
  )
}
