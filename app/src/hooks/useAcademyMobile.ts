import { useEffect, useState } from 'react'

/** Shortest full-screen edge at or above this is a tablet (always desktop). */
export const ACADEMY_TABLET_SHORT_EDGE_PX = 600

/**
 * Academy mobile layout: full-screen portrait phones only.
 * Uses window.screen (device), not the browser viewport, so browser chrome
 * and soft keyboards do not flip the mode. Tablets stay desktop even in
 * portrait via the short-edge floor.
 */
export function isAcademyMobileScreen(
  screenLike: Pick<Screen, 'width' | 'height'> = window.screen,
): boolean {
  const { width, height } = screenLike
  if (!(width > 0) || !(height > 0)) return false
  if (Math.min(width, height) >= ACADEMY_TABLET_SHORT_EDGE_PX) return false
  return height > width
}

function readAcademyMobile(): boolean {
  if (typeof window === 'undefined') return false
  return isAcademyMobileScreen(window.screen)
}

export function useAcademyMobile(): boolean {
  const [mobile, setMobile] = useState(readAcademyMobile)

  useEffect(() => {
    const sync = () => setMobile(readAcademyMobile())
    sync()
    window.addEventListener('orientationchange', sync)
    window.addEventListener('resize', sync)
    return () => {
      window.removeEventListener('orientationchange', sync)
      window.removeEventListener('resize', sync)
    }
  }, [])

  return mobile
}
