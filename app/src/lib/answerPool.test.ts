import { describe, expect, it } from 'vitest'
import { drawOptions, pickVariants, seededRng, type AnswerPool } from './answerPool'

const pool: AnswerPool = {
  correct: ['Friction', 'Resistance to action'],
  distractors: [
    { text: 'Chance', misconception: 'A different characteristic.' },
    { text: 'War', misconception: 'The whole, not the part.' },
    { text: 'Policy', misconception: 'A purpose, not a force.' },
    { text: 'Disorder', misconception: 'A result, not the cause.' },
  ],
  show_count: 4,
}

describe('drawOptions', () => {
  it('draws the same options for the same seed', () => {
    const first = drawOptions(pool, 'multiple_choice', seededRng(7))
    const second = drawOptions(pool, 'multiple_choice', seededRng(7))
    expect(second).toEqual(first)
  })

  it('shows the requested count with exactly one correct answer', () => {
    const drawn = drawOptions(pool, 'multiple_choice', seededRng(3))
    expect(drawn.options).toHaveLength(4)
    expect(drawn.correct).toHaveLength(1)
    expect(drawn.options.filter((option) => drawn.correct.includes(option))).toHaveLength(1)
    expect(drawn.options.every((option) => pool.correct.includes(option) || pool.distractors.some((row) => row.text === option))).toBe(true)
  })

  it('keeps at least two correct answers for multiple select', () => {
    const drawn = drawOptions(pool, 'multiple_select', seededRng(11))
    expect(drawn.correct.length).toBeGreaterThanOrEqual(2)
    expect(drawn.correct.every((answer) => drawn.options.includes(answer))).toBe(true)
    expect(drawn.options).toHaveLength(4)
  })
})

describe('pickVariants', () => {
  const quizzes = [
    { id: 'a1', citations: [{ uri: 'wiki://friction' }] },
    { id: 'a2', citations: [{ uri: 'wiki://friction' }] },
    { id: 'b1', citations: [{ uri: 'wiki://chance' }] },
    { id: 'loose', citations: [] },
  ]

  it('keeps one quiz per wiki entry and every quiz without a citation', () => {
    const picked = pickVariants(quizzes, seededRng(2))
    const ids = picked.map((quiz) => quiz.id)
    expect(ids.filter((id) => id === 'a1' || id === 'a2')).toHaveLength(1)
    expect(ids).toContain('b1')
    expect(ids).toContain('loose')
  })

  it('keeps a requested variant even when another would be drawn', () => {
    const picked = pickVariants(quizzes, seededRng(2), new Set(['a2']))
    expect(picked.map((quiz) => quiz.id)).toContain('a2')
    expect(picked.map((quiz) => quiz.id)).not.toContain('a1')
  })
})
