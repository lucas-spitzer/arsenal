import { describe, expect, it } from 'vitest'
import {
  academyPageForRole,
  academyRailForRole,
  defaultAcademyPage,
  quizLaunchFromScope,
  showsFlashcardDeck,
} from './types'

describe('quizLaunchFromScope', () => {
  it('opens a Subject Exam on the class first, then the book', () => {
    expect(quizLaunchFromScope({ sourceId: 'src-1', lessonId: 'les-1' })).toEqual({
      mode: 'subject',
      subjectKind: 'lesson',
      subjectId: 'les-1',
    })
    expect(quizLaunchFromScope({ sourceId: 'src-1', lessonId: null })).toEqual({
      mode: 'subject',
      subjectKind: 'source',
      subjectId: 'src-1',
    })
  })

  it('defaults to the Full Exam without a subject', () => {
    expect(quizLaunchFromScope({ sourceId: null })).toEqual({
      mode: 'full_practice',
      subjectKind: 'source',
      subjectId: '',
    })
  })
})

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

  it('keeps challenge pages open to admin while student access is closed', () => {
    const admin = academyRailForRole(true, false).map((item) => item.id)
    expect(admin).toEqual(expect.arrayContaining(['leaderboard', 'quiz', 'flashcards', 'analytics']))
    expect(academyPageForRole('quiz', true, false)).toBe('quiz')
    expect(academyPageForRole('leaderboard', true, false)).toBe('leaderboard')
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

  it('keeps the flip-card deck with Academics after challenge pages open', () => {
    expect(showsFlashcardDeck(true)).toBe(true)
    expect(showsFlashcardDeck(false)).toBe(false)
    expect(academyRailForRole(false, true).map((item) => item.id)).toContain('flashcards')
    expect(academyPageForRole('flashcards', false, true)).toBe('flashcards')
  })
})
