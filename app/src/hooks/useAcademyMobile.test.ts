import { describe, expect, it } from 'vitest'
import { ACADEMY_TABLET_SHORT_EDGE_PX, isAcademyMobileScreen } from './useAcademyMobile'

describe('isAcademyMobileScreen', () => {
  it('treats portrait phones as mobile', () => {
    expect(isAcademyMobileScreen({ width: 390, height: 844 })).toBe(true)
    expect(isAcademyMobileScreen({ width: 360, height: 800 })).toBe(true)
  })

  it('treats landscape phones as desktop', () => {
    expect(isAcademyMobileScreen({ width: 844, height: 390 })).toBe(false)
  })

  it('treats tablets as desktop in portrait and landscape', () => {
    expect(isAcademyMobileScreen({ width: 768, height: 1024 })).toBe(false)
    expect(isAcademyMobileScreen({ width: 1024, height: 768 })).toBe(false)
    expect(
      isAcademyMobileScreen({
        width: ACADEMY_TABLET_SHORT_EDGE_PX,
        height: ACADEMY_TABLET_SHORT_EDGE_PX + 200,
      }),
    ).toBe(false)
  })

  it('rejects invalid screen sizes', () => {
    expect(isAcademyMobileScreen({ width: 0, height: 800 })).toBe(false)
    expect(isAcademyMobileScreen({ width: 390, height: 0 })).toBe(false)
  })
})
