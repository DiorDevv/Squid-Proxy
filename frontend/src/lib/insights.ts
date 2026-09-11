import type { TranslationKey } from '@/i18n'
import { CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { METRIC_LABEL_KEYS, isByteMetric } from '@/lib/alertRules'
import { formatBytes, formatNumber } from '@/lib/format'
import type { AlertRuleMetric, AnomalyEvent, DomainCategoryLabel } from '@/types/api'

type Translate = (key: TranslationKey, vars?: Record<string, string | number>) => string

const ANOMALY_KEYS: Record<string, { title: TranslationKey; description: TranslationKey }> = {
  traffic_spike: {
    title: 'insights.anomaly.trafficSpike.title',
    description: 'insights.anomaly.trafficSpike.description',
  },
  new_blocked_domain: {
    title: 'insights.anomaly.newBlockedDomain.title',
    description: 'insights.anomaly.newBlockedDomain.description',
  },
  client_blocked_ratio: {
    title: 'insights.anomaly.clientBlockedRatio.title',
    description: 'insights.anomaly.clientBlockedRatio.description',
  },
  sensitive_category_visit: {
    title: 'insights.anomaly.sensitiveCategoryVisit.title',
    description: 'insights.anomaly.sensitiveCategoryVisit.description',
  },
  excessive_non_work_category_time: {
    title: 'insights.anomaly.excessiveNonWorkCategoryTime.title',
    description: 'insights.anomaly.excessiveNonWorkCategoryTime.description',
  },
  client_quota_exceeded: {
    title: 'insights.anomaly.clientQuotaExceeded.title',
    description: 'insights.anomaly.clientQuotaExceeded.description',
  },
  uncategorized_domain_high_traffic: {
    title: 'insights.anomaly.uncategorizedDomainHighTraffic.title',
    description: 'insights.anomaly.uncategorizedDomainHighTraffic.description',
  },
  export_not_downloaded: {
    title: 'insights.anomaly.exportNotDownloaded.title',
    description: 'insights.anomaly.exportNotDownloaded.description',
  },
  watchlist_hit: {
    title: 'insights.anomaly.watchlistHit.title',
    description: 'insights.anomaly.watchlistHit.description',
  },
}

/** Re-renders an anomaly's title/description in the user's chosen UI
 * language from its `kind`/`params` (see app/insights/base.py), falling
 * back to the stored English text for older rows that predate kind/params
 * (both NULL) or for a kind this frontend build doesn't recognize yet. */
export function localizeAnomaly(item: AnomalyEvent, t: Translate): { title: string; description: string } {
  // Custom rules (Settings -> Alerts -> Custom rules) get a per-rule kind
  // ("custom_rule_<id>") so cooldown dedup stays per-rule -- but there's no
  // way to pre-register an i18n key for an admin-created rule's id, so
  // every one of them shares this single generic template instead, filled
  // in from params. See app/insights/anomaly.py's _custom_rules.
  if (item.kind?.startsWith('custom_rule_') && item.params) {
    const metric = item.params.metric as AlertRuleMetric | undefined
    const format = metric && isByteMetric(metric) ? formatBytes : formatNumber
    const metricLabel = metric ? t(METRIC_LABEL_KEYS[metric]) : String(item.params.metric ?? '')
    return {
      title: item.params.ruleName ? String(item.params.ruleName) : item.title,
      description: t('insights.anomaly.customRule.description', {
        target: String(item.params.target ?? ''),
        metric: metricLabel,
        value: format(Number(item.params.value ?? 0)),
        threshold: format(Number(item.params.threshold ?? 0)),
        windowMinutes: item.params.windowMinutes ?? '',
      }),
    }
  }

  const keys = item.kind ? ANOMALY_KEYS[item.kind] : undefined
  if (!keys || !item.params) {
    return { title: item.title, description: item.description }
  }

  const vars = { ...item.params }
  if (item.kind === 'sensitive_category_visit' && typeof vars.category === 'string') {
    const categoryKey = CATEGORY_LABEL_KEYS[vars.category as DomainCategoryLabel]
    vars.category = categoryKey ? t(categoryKey) : vars.category
  }

  return { title: t(keys.title, vars), description: t(keys.description, vars) }
}
