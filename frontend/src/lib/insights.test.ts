import { describe, expect, it } from 'vitest'
import { localizeAnomaly } from '@/lib/insights'
import { translate } from '@/i18n'
import type { AnomalyEvent } from '@/types/api'

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) =>
  translate('en', key, vars)

function baseEvent(overrides: Partial<AnomalyEvent>): AnomalyEvent {
  return {
    id: '1',
    generated_at: '2026-09-11T10:00:00Z',
    title: 'fallback title',
    description: 'fallback description',
    severity: 'high',
    client_ip: null,
    domain: null,
    branch: 'default',
    kind: null,
    params: null,
    ...overrides,
  }
}

describe('localizeAnomaly', () => {
  it('falls back to the stored English text for an unrecognized kind', () => {
    const item = baseEvent({ kind: 'some_future_kind', params: {} })
    expect(localizeAnomaly(item, t)).toEqual({ title: 'fallback title', description: 'fallback description' })
  })

  it('localizes a known built-in kind from its params', () => {
    const item = baseEvent({
      kind: 'traffic_spike',
      params: { current: 40, baseline: 10, windows: 6 },
    })
    const result = localizeAnomaly(item, t)
    expect(result.title).toBe('Traffic spike detected')
    expect(result.description).toContain('40 requests')
    expect(result.description).toContain('~10')
  })

  it('localizes a custom rule (byte metric) with the rule name as title and MB-formatted values', () => {
    const item = baseEvent({
      kind: 'custom_rule_5',
      client_ip: '10.0.0.5',
      params: {
        ruleName: 'IP data spike',
        scope: 'client_ip',
        metric: 'total_bytes',
        target: '10.0.0.5',
        value: 60_000_000,
        threshold: 50_000_000,
        windowMinutes: 10,
      },
    })
    const result = localizeAnomaly(item, t)
    expect(result.title).toBe('IP data spike')
    expect(result.description).toBe('10.0.0.5 reached 57.2 MB (Data downloaded) in the last 10 min (threshold: 47.7 MB).')
  })

  it('localizes a custom rule (count metric) without byte formatting', () => {
    const item = baseEvent({
      kind: 'custom_rule_9',
      domain: 'example.com',
      params: {
        ruleName: 'Domain request spike',
        scope: 'domain',
        metric: 'request_count',
        target: 'example.com',
        value: 150,
        threshold: 100,
        windowMinutes: 10,
      },
    })
    const result = localizeAnomaly(item, t)
    expect(result.title).toBe('Domain request spike')
    expect(result.description).toBe(
      'example.com reached 150 (Requests) in the last 10 min (threshold: 100).',
    )
  })

  it('handles a custom rule kind with no params by falling back to stored text', () => {
    const item = baseEvent({ kind: 'custom_rule_5', params: null })
    expect(localizeAnomaly(item, t)).toEqual({ title: 'fallback title', description: 'fallback description' })
  })
})
