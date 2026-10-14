import { describe, expect, it } from 'vitest'
import { firstSettingsPage, visibleSettingsItems } from '@/pages/settings/settings-nav'

const pages = (...args: Parameters<typeof visibleSettingsItems>) =>
  visibleSettingsItems(...args).map((item) => item.to)

describe('visibleSettingsItems', () => {
  it('shows an unrestricted admin every page, including the global Telegram one', () => {
    expect(pages('admin', [], true)).toEqual(['general', 'users', 'retention', 'telegram'])
    expect(pages('superadmin', ['audit', 'watchlist'], true)).toContain('audit')
  })

  it('hides the global Telegram page from a branch-limited admin', () => {
    expect(pages('admin', [], false)).not.toContain('telegram')
  })

  it('opens pages to a viewer by permission only', () => {
    expect(pages('viewer', ['watchlist'], true)).toEqual(['watchlist'])
    expect(pages('viewer', ['alerts'], true)).toEqual(['categories'])
    expect(pages('viewer', [], true)).toEqual([])
  })

  it('gives an auditor the oversight pages', () => {
    expect(pages('auditor', ['audit', 'export'], true)).toEqual([
      'audit',
      'policy',
      'system-health',
    ])
  })
})

describe('firstSettingsPage', () => {
  it('lands an admin on General and others on their first page', () => {
    expect(firstSettingsPage('admin', [])).toBe('general')
    expect(firstSettingsPage('auditor', ['audit'])).toBe('audit')
    expect(firstSettingsPage('viewer', ['raw_export'])).toBe('export')
  })
})
