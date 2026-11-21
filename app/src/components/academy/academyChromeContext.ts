import { createContext, useContext } from 'react'

export type AcademyChromeValue = {
  /** Portrait phone Academy layout. Desktop/landscape stays false. */
  compact: boolean
}

const AcademyChromeContext = createContext<AcademyChromeValue>({ compact: false })

export const AcademyChromeProvider = AcademyChromeContext.Provider

export function useAcademyChrome(): AcademyChromeValue {
  return useContext(AcademyChromeContext)
}
