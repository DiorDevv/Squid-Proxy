import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type BrandTheme = 'amber' | 'azure' | 'violet'

export const BRAND_THEMES: BrandTheme[] = ['amber', 'azure', 'violet']

interface ThemeState {
  brand: BrandTheme
  setBrand: (brand: BrandTheme) => void
}

function applyBrand(brand: BrandTheme): void {
  document.documentElement.setAttribute('data-brand', brand)
}

/** Which shared primary-action/warning/blocked accent hue is active (see
 * index.css's `:root[data-brand=...]` blocks). Persisted so the choice
 * survives a reload; applied eagerly (both here and in onRehydrateStorage)
 * to avoid a flash of the default theme before rehydration completes. */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      brand: 'amber',
      setBrand: (brand) => {
        applyBrand(brand)
        set({ brand })
      },
    }),
    {
      name: 'squid-watch-theme',
      onRehydrateStorage: () => (state) => {
        if (state) applyBrand(state.brand)
      },
    },
  ),
)

applyBrand(useThemeStore.getState().brand)
