import { describe, expect, it } from 'vitest'
import { RISK_BAND_STYLES, formatRiskRawValue, riskBand } from '@/lib/risk'

describe('riskBand', () => {
  it('bands the composite score the same way the backend does', () => {
    expect(riskBand(0)).toBe('low')
    expect(riskBand(39.9)).toBe('low')
    expect(riskBand(40)).toBe('medium')
    expect(riskBand(69.9)).toBe('medium')
    expect(riskBand(70)).toBe('high')
    expect(riskBand(100)).toBe('high')
  })

  it('has a style entry for every band', () => {
    for (const band of ['low', 'medium', 'high'] as const) {
      expect(RISK_BAND_STYLES[band].hex).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })
})

describe('formatRiskRawValue', () => {
  it('renders the two ratio signals as percentages', () => {
    expect(formatRiskRawValue('blocked_ratio', 0.073)).toBe('7.3%')
    expect(formatRiskRawValue('sensitive_traffic', 0.6)).toBe('60.0%')
  })

  it('renders count signals as rounded integers', () => {
    expect(formatRiskRawValue('anomalies', 8)).toBe('8')
    expect(formatRiskRawValue('quota_breaches', 2.0)).toBe('2')
    expect(formatRiskRawValue('uncategorized_domains', 3.4)).toBe('3')
  })
})
