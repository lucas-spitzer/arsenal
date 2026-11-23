import { createContext, useContext } from 'react'
import type { AtlasMe } from '../../lib/atlasApi'

export type AtlasContextValue = {
  me: AtlasMe | null
  studentAccess: boolean
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
  setLifetimeAp: (lifetimeAp: number) => void
}

export const AtlasContext = createContext<AtlasContextValue | null>(null)

export function useAtlas(): AtlasContextValue {
  const value = useContext(AtlasContext)
  if (!value) {
    throw new Error('useAtlas must be used inside AtlasProvider.')
  }
  return value
}
