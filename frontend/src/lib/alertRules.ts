import type { TranslationKey } from '@/i18n'
import type { AlertRuleMetric, AlertRuleScope } from '@/types/api'

/** Single source of truth for custom-alert-rule scope/metric labels --
 * shared by the Settings -> Alerts rule editor (AlertRulesPanel) and the
 * anomaly localizer (lib/insights.ts), which both need to turn the same
 * raw enum values into the same translated words. */
export const SCOPE_LABEL_KEYS: Record<AlertRuleScope, TranslationKey> = {
  client_ip: 'settings.alertRules.scopeClientIp',
  domain: 'settings.alertRules.scopeDomain',
  branch: 'settings.alertRules.scopeBranch',
}

export const METRIC_LABEL_KEYS: Record<AlertRuleMetric, TranslationKey> = {
  request_count: 'settings.alertRules.metricRequestCount',
  blocked_count: 'settings.alertRules.metricBlockedCount',
  total_bytes: 'settings.alertRules.metricTotalBytes',
  bytes_received: 'settings.alertRules.metricBytesReceived',
}

export function isByteMetric(metric: AlertRuleMetric): boolean {
  return metric === 'total_bytes' || metric === 'bytes_received'
}
