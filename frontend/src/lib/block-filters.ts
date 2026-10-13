import { useSearchParams } from 'react-router-dom'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { TranslationKey } from '@/i18n'
import type { BlockGroupBy, BlockGroupSort, BlockKind } from '@/types/api'

/** The Blocked page's shared filters (backend app/services/block_filters.py
 * defines the term language). Kept in the URL so a link reproduces the view
 * exactly and the browser's Back button undoes a drill-down. */
export interface BlockFilterValues {
  domains: string
  clients: string
  users: string
  proxy: string
}

export type BlockView = 'requests' | 'analysis'
/** The Requests view can also list every request, blocked or not. */
export type BlockOutcome = BlockKind | 'everything'

const KEYS = { domains: 'd', clients: 'c', users: 'u', proxy: 'p' } as const
const GROUPS: BlockGroupBy[] = ['domain', 'client', 'user', 'subnet', 'branch', 'proxy']
const SORTS: BlockGroupSort[] = ['requests', 'clients', 'users', 'domains', 'last', 'key']
const OUTCOMES: BlockOutcome[] = ['denied', 'auth', 'all', 'everything']

export const EMPTY_FILTERS: BlockFilterValues = { domains: '', clients: '', users: '', proxy: '' }

export interface BlockPageState {
  view: BlockView
  group: BlockGroupBy
  sort: BlockGroupSort
  outcome: BlockOutcome
  filters: BlockFilterValues
}

export interface BlockPagePatch extends Partial<Omit<BlockPageState, 'filters'>> {
  filters?: Partial<BlockFilterValues>
}

function pick<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
}

export function useBlockPageState() {
  const [params, setParams] = useSearchParams()
  const state: BlockPageState = {
    view: params.get('view') === 'analysis' ? 'analysis' : 'requests',
    group: pick(params.get('g'), GROUPS, 'domain'),
    sort: pick(params.get('sort'), SORTS, 'requests'),
    // A real block is the default: a 407 is the proxy asking for a login.
    outcome: pick(params.get('kind'), OUTCOMES, 'denied'),
    filters: {
      domains: params.get(KEYS.domains) ?? '',
      clients: params.get(KEYS.clients) ?? '',
      users: params.get(KEYS.users) ?? '',
      proxy: params.get(KEYS.proxy) ?? '',
    },
  }

  /** `push` adds a history entry (a drill-down the user may want to step
   * back from); everything else replaces the current one. */
  function update(patch: BlockPagePatch, { push = false }: { push?: boolean } = {}) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        const set = (key: string, value: string | undefined, fallback?: string) => {
          if (value === undefined) return
          if (!value || value === fallback) next.delete(key)
          else next.set(key, value)
        }
        set('view', patch.view, 'requests')
        set('g', patch.group, 'domain')
        set('sort', patch.sort, 'requests')
        set('kind', patch.outcome, 'denied')
        for (const [name, key] of Object.entries(KEYS)) {
          set(key, patch.filters?.[name as keyof BlockFilterValues]?.trim())
        }
        return next
      },
      { replace: !push },
    )
  }

  return { ...state, update }
}

/** The filter values as API query params (empty ones left out). */
export function filterParams(filters: BlockFilterValues): Record<string, string | undefined> {
  return {
    domains: filters.domains.trim() || undefined,
    clients: filters.clients.trim() || undefined,
    users: filters.users.trim() || undefined,
    proxy: filters.proxy.trim() || undefined,
  }
}

export const GROUP_LABELS: Record<BlockGroupBy, TranslationKey> = {
  domain: 'blocked.group.domain',
  client: 'blocked.group.client',
  user: 'blocked.group.user',
  subnet: 'blocked.group.subnet',
  branch: 'blocked.group.branch',
  proxy: 'blocked.group.proxy',
}

/** '' means "no login" for a login and "no proxy label" for a proxy. */
export function groupKeyLabel(t: (key: TranslationKey) => string, group: BlockGroupBy, key: string): string {
  return key || (group === 'user' ? t('blocked.group.noLogin') : t('blocked.group.noProxy'))
}

export function splitTerms(value: string): string[] {
  return value.split(/[\s,;]+/).filter(Boolean)
}

export interface BlockPreset {
  id: string
  name: string
  filters: BlockFilterValues
  builtIn?: boolean
}

/** Ready-made filters for the questions asked most often. */
export const BUILT_IN_PRESETS: BlockPreset[] = [
  {
    id: 'certificates',
    name: 'blocked.presets.certificates',
    builtIn: true,
    filters: { ...EMPTY_FILTERS, domains: 'crl. ocsp. ctldl.windowsupdate.com pki.goog' },
  },
  {
    id: 'windows-update',
    name: 'blocked.presets.windowsUpdate',
    builtIn: true,
    filters: {
      ...EMPTY_FILTERS,
      domains: 'windowsupdate.com update.microsoft.com delivery.mp.microsoft.com',
    },
  },
]

function generateId(): string {
  // crypto.randomUUID() is missing over plain HTTP (see saved-filters-store.ts).
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

interface BlockPresetsState {
  items: BlockPreset[]
  save: (name: string, filters: BlockFilterValues) => void
  remove: (id: string) => void
}

/** Per-browser saved filter sets -- UI convenience, like saved-filters-store. */
export const useBlockPresetsStore = create<BlockPresetsState>()(
  persist(
    (set) => ({
      items: [],
      save: (name, filters) =>
        set((state) => ({ items: [...state.items, { id: generateId(), name, filters }] })),
      remove: (id) => set((state) => ({ items: state.items.filter((item) => item.id !== id) })),
    }),
    { name: 'squid-watch-block-presets' },
  ),
)
