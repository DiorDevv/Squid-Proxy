import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { RangeParam } from '@/types/api'

/** crypto.randomUUID() only exists in secure contexts (HTTPS or
 * http://localhost) -- this dashboard is commonly opened over plain HTTP via
 * a bare VM IP (see vm-test-qollanma/*.md), where it's undefined. This id is
 * just a React key/removal handle, not security-sensitive, so a non-crypto
 * fallback is fine. */
function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

/** A named snapshot of useFiltersStore's shape (lib/filters-store.ts) --
 * range/branch is the one filter combination shared across Dashboard/
 * Domains/Clients/Blocked (see ARCHITECTURE.md), so a saved preset applies
 * cleanly on any of them regardless of which page it was saved from. */
export interface SavedFilter {
  id: string
  name: string
  mode: 'preset' | 'custom'
  range: RangeParam
  customFrom: string | null
  customTo: string | null
  branch: string | null
}

interface SavedFiltersState {
  items: SavedFilter[]
  save: (filter: Omit<SavedFilter, 'id'>) => void
  remove: (id: string) => void
}

/** Persisted client-side only, same reasoning as notifications-store.ts --
 * this is per-browser UI convenience, not data any other admin or the
 * backend needs to know about. */
export const useSavedFiltersStore = create<SavedFiltersState>()(
  persist(
    (set) => ({
      items: [],
      save: (filter) =>
        set((state) => ({
          items: [...state.items, { ...filter, id: generateId() }],
        })),
      remove: (id) => set((state) => ({ items: state.items.filter((item) => item.id !== id) })),
    }),
    { name: 'squid-watch-saved-filters' },
  ),
)
