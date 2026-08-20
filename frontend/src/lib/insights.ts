import type { TranslationKey } from '@/i18n'
import { CATEGORY_LABEL_KEYS } from '@/lib/categories'
import type { AnomalyEvent, DomainCategoryLabel } from '@/types/api'

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
}

/** Re-renders an anomaly's title/description in the user's chosen UI
 * language from its `kind`/`params` (see app/insights/base.py), falling
 * back to the stored English text for older rows that predate kind/params
 * (both NULL) or for a kind this frontend build doesn't recognize yet. */
export function localizeAnomaly(item: AnomalyEvent, t: Translate): { title: string; description: string } {
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
