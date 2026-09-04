import type { TranslationKey } from '@/i18n'
import type { DomainCategoryLabel } from '@/types/api'

/** Single source of truth for the fixed category set -- shared by the
 * Settings admin panel (assigning a category), the Domains page's usage
 * breakdown, and its category filter, so the three never drift out of sync
 * with each other or with the backend's DomainCategoryLabel enum. */
export const CATEGORY_OPTIONS: DomainCategoryLabel[] = [
  'uncategorized',
  'social_media',
  'video_streaming',
  'music_streaming',
  'gaming',
  'work_tools',
  'shopping',
  'news',
  'gambling',
  'adult_content',
  'other',
]

/** Fixed hex per category for multi-series charts (the category trend
 * stacked area). Deliberately literal hex, not theme tokens: the same
 * category must keep the same color across brand themes so a stacked chart
 * stays readable. The two sensitive categories are intentionally red/pink
 * so "risky" traffic reads as risky at a glance. */
export const CATEGORY_COLORS: Record<DomainCategoryLabel, string> = {
  uncategorized: '#94a3b8',
  social_media: '#3b82f6',
  video_streaming: '#a855f7',
  music_streaming: '#14b8a6',
  gaming: '#f59e0b',
  work_tools: '#22c55e',
  shopping: '#eab308',
  news: '#6366f1',
  gambling: '#ef4444',
  adult_content: '#db2777',
  other: '#64748b',
}

/** Categories treated as inherently higher-risk -- surfaced in red on the
 * analytics views and weighted into the per-branch risk score's
 * "sensitive traffic" signal (see backend alert_settings; an admin can
 * additionally mark any category sensitive per branch). */
export const SENSITIVE_CATEGORIES: DomainCategoryLabel[] = ['gambling', 'adult_content']

export const CATEGORY_LABEL_KEYS: Record<DomainCategoryLabel, TranslationKey> = {
  uncategorized: 'category.uncategorized',
  social_media: 'category.socialMedia',
  video_streaming: 'category.videoStreaming',
  music_streaming: 'category.musicStreaming',
  gaming: 'category.gaming',
  work_tools: 'category.workTools',
  shopping: 'category.shopping',
  news: 'category.news',
  gambling: 'category.gambling',
  adult_content: 'category.adultContent',
  other: 'category.other',
}
