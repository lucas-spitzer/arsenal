import { describe, expect, it } from 'vitest'
import { accuracyPercent, resultBatchKey, summarizeQuizResults } from './quizAnalytics'
import type { QuizResult } from './quizResultsApi'

function result(overrides: Partial<QuizResult> = {}): QuizResult {
  return {
    id: 'result-1',
    workspace_id: 'ws-1',
    knowledge_project_id: 'proj-1',
    source_id: 'src-1',
    title: 'Chapter 1',
    scope: 'one_per_term',
    correct_count: 1,
    question_count: 2,
    completed_at: '2026-10-28T12:00:00Z',
    answers: [
      {
        quiz_id: 'q1',
        wiki_id: 'wiki-friction',
        question: 'What resists action?',
        selected: 'Chance',
        answer: 'Friction',
        correct: false,
      },
      {
        quiz_id: 'q2',
        wiki_id: 'wiki-war',
        question: 'What is war?',
        selected: 'A duel',
        answer: 'A duel',
        correct: true,
      },
    ],
    ...overrides,
  }
}

describe('summarizeQuizResults', () => {
  it('totals every finished quiz and ranks missed terms first', () => {
    const older = result({
      id: 'older',
      completed_at: '2026-10-01T12:00:00Z',
      correct_count: 0,
      question_count: 1,
      answers: [
        {
          quiz_id: 'q1',
          wiki_id: 'wiki-friction',
          question: 'What resists action?',
          selected: 'Chance',
          answer: 'Friction',
          correct: false,
        },
      ],
    })
    const summary = summarizeQuizResults([result(), older], {
      batchKey: 'all',
      wikiLabels: new Map([['wiki-friction', 'Friction']]),
    })

    expect(summary.quizzesTaken).toBe(2)
    expect(summary.questionsAnswered).toBe(3)
    expect(summary.accuracy).toBe(accuracyPercent(1, 3))
    expect(summary.recent.map((item) => item.id)).toEqual(['result-1', 'older'])
    expect(summary.needsWork[0]).toMatchObject({
      label: 'Friction',
      correct: 0,
      answered: 2,
      projectId: 'proj-1',
    })
    expect(summary.needsWork.some((term) => term.label === 'What is war?')).toBe(false)
    expect(summary.batches).toEqual([
      { key: resultBatchKey(result()), title: 'Chapter 1', quizzesTaken: 2, questionsAnswered: 3, correct: 1 },
    ])
  })

  it('narrows every figure to one batch', () => {
    const other = result({
      id: 'other',
      knowledge_project_id: 'proj-2',
      title: 'Chapter 2',
      correct_count: 1,
      question_count: 1,
      answers: [
        {
          quiz_id: 'q9',
          wiki_id: null,
          question: 'Name the estimate.',
          selected: 'Time',
          answer: 'Space',
          correct: false,
        },
      ],
    })
    const summary = summarizeQuizResults([result(), other], {
      batchKey: 'proj-2',
      wikiLabels: new Map(),
    })
    expect(summary.quizzesTaken).toBe(1)
    expect(summary.needsWork.map((term) => term.label)).toEqual(['Name the estimate.'])
    expect(summary.batches.map((batch) => batch.title)).toEqual(['Chapter 2'])
  })
})
