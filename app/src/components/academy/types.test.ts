import { describe, expect, it } from 'vitest'
import { academyPageForRole, academyRailForRole, defaultAcademyPage } from './types'

describe('academy rail gating', () => {
  it('defaults admin to leaderboard and students to calendar until access opens', () => {
    expect(defaultAcademyPage(true)).toBe('leaderboard')
    expect(defaultAcademyPage(false, false)).toBe('calendar')
    expect(defaultAcademyPage(false, true)).toBe('leaderboard')
  })

  it('hides challenge pages from students until access opens', () => {
    const closed = academyRailForRole(false, false).map((item) => item.id)
    expect(closed).not.toContain('leaderboard')
    expect(closed).not.toContain('quiz')
    expect(closed).not.toContain('flashcards')
    expect(closed).not.toContain('analytics')
    expect(closed).toContain('calendar')

    const open = academyRailForRole(false, true).map((item) => item.id)
    expect(open).toContain('leaderboard')
    expect(open).toContain('quiz')
    expect(open).toContain('analytics')
    expect(open).not.toContain('scenarios')
  })

  it('omits scenarios from the rail for every role', () => {
    expect(academyRailForRole(true).map((item) => item.id)).not.toContain('scenarios')
    expect(academyRailForRole(false, true).map((item) => item.id)).not.toContain('scenarios')
  })

  it('keeps scenarios admin-only even with student access', () => {
    expect(academyPageForRole('scenarios', false, true)).toBe('leaderboard')
    expect(academyPageForRole('quiz', false, false)).toBe('calendar')
    expect(academyPageForRole('quiz', false, true)).toBe('quiz')
  })
})
