import { AlertTriangle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ConfigFinding, ConfigFindingCode } from '@/types/api'

const TITLE_KEYS: Record<ConfigFindingCode, TranslationKey> = {
  no_caching: 'analytics.advisor.noCaching.title',
  no_proxy_auth: 'analytics.advisor.noProxyAuth.title',
  no_denies: 'analytics.advisor.noDenies.title',
  sensitive_allowed: 'analytics.advisor.sensitiveAllowed.title',
  single_domain_dominant: 'analytics.advisor.singleDomain.title',
}
const DESC_KEYS: Record<ConfigFindingCode, TranslationKey> = {
  no_caching: 'analytics.advisor.noCaching.desc',
  no_proxy_auth: 'analytics.advisor.noProxyAuth.desc',
  no_denies: 'analytics.advisor.noDenies.desc',
  sensitive_allowed: 'analytics.advisor.sensitiveAllowed.desc',
  single_domain_dominant: 'analytics.advisor.singleDomain.desc',
}

/** How each finding's `value` should read next to its text. */
function formatValue(f: ConfigFinding): string {
  switch (f.code) {
    case 'sensitive_allowed':
      return formatNumber(Math.round(f.value))
    case 'single_domain_dominant':
      return `${(f.value * 100).toFixed(0)}% · ${f.detail ?? ''}`
    default:
      return `${(f.value * 100).toFixed(1)}%`
  }
}

interface ConfigAdvisorPanelProps {
  findings: ConfigFinding[]
}

/** Squid-config advice for the Overview tab. Only rendered when there's at
 * least one finding (see AnalyticsOverviewPage) -- a healthy deployment
 * never sees it. */
export function ConfigAdvisorPanel({ findings }: ConfigAdvisorPanelProps) {
  const { t } = useTranslation()

  return (
    <ul className="flex flex-col divide-y divide-border">
      {findings.map((f) => {
        const warn = f.severity === 'warning'
        const Icon = warn ? AlertTriangle : Info
        return (
          <li key={f.code} className="flex items-start gap-3 py-2.5">
            <Icon
              className={cn('mt-0.5 h-4 w-4 shrink-0', warn ? 'text-amber-500' : 'text-info')}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-foreground">{t(TITLE_KEYS[f.code])}</span>
                <span className="font-data shrink-0 text-xs text-muted-foreground">{formatValue(f)}</span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">{t(DESC_KEYS[f.code])}</p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
