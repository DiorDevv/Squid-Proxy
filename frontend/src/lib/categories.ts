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
