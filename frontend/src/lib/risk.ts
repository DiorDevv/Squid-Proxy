import type { TranslationKey } from '@/i18n'
import type { RiskBand, RiskSignalKey } from '@/types/api'

/** Band thresholds mirror the backend risk model
 * (app/services/analytics_service.py: _RISK_BAND_MEDIUM / _RISK_BAND_HIGH).
 * Kept here too so the frontend can band a score locally without a
 * round-trip. */
export function riskBand(score: number): RiskBand {
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

interface BandStyle {
  /** text color class */
  text: string
  /** faint fill class for a chip/row background */
  bg: string
  border: string
  /** solid fill for a bar/dot */
  bar: string
  /** literal hex for chart fills (theme tokens shift per brand; risk
   * semantics must not) */
  hex: string
}

/** low = green, medium = amber, high = red -- all three are brand-stable
 * (the app's `--warning` token shifts blue/purple per theme, so medium
 * uses a literal amber instead). */
export const RISK_BAND_STYLES: Record<RiskBand, BandStyle> = {
  low: {
    text: 'text-success',
    bg: 'bg-success/10',
    border: 'border-success/30',
    bar: 'bg-success',
    hex: '#22c55e',
  },
  medium: {
    text: 'text-amber-500',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    bar: 'bg-amber-500',
    hex: '#f59e0b',
  },
  high: {
    text: 'text-destructive',
    bg: 'bg-destructive/10',
    border: 'border-destructive/30',
    bar: 'bg-destructive',
    hex: '#ef4444',
  },
}

export const RISK_BAND_LABEL_KEYS: Record<RiskBand, TranslationKey> = {
  low: 'analytics.risk.bandLow',
  medium: 'analytics.risk.bandMedium',
  high: 'analytics.risk.bandHigh',
}

export const RISK_SIGNAL_LABEL_KEYS: Record<RiskSignalKey, TranslationKey> = {
  blocked_ratio: 'analytics.risk.signalBlockedRatio',
  sensitive_traffic: 'analytics.risk.signalSensitiveTraffic',
  anomalies: 'analytics.risk.signalAnomalies',
  quota_breaches: 'analytics.risk.signalQuotaBreaches',
  uncategorized_domains: 'analytics.risk.signalUncategorizedDomains',
}

/** A stable color per signal for the stacked contribution bar in the risk
 * table -- ordered darkest→lightest roughly by the backend's weights. */
export const RISK_SIGNAL_COLORS: Record<RiskSignalKey, string> = {
  blocked_ratio: '#ef4444',
  sensitive_traffic: '#db2777',
  anomalies: '#f59e0b',
  quota_breaches: '#a855f7',
  uncategorized_domains: '#64748b',
}

/** Human-readable rendering of a signal's raw value: a ratio for the two
 * ratio signals, a plain count otherwise. */
export function formatRiskRawValue(key: RiskSignalKey, raw: number): string {
  if (key === 'blocked_ratio' || key === 'sensitive_traffic') {
    return `${(raw * 100).toFixed(1)}%`
  }
  return String(Math.round(raw))
}
