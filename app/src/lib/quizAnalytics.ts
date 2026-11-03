import type { QuizResult } from './quizResultsApi'

export const NEEDS_WORK_CAP = 8
const ALL_BATCHES = 'all'

export interface BatchAccuracy {
  key: string
  title: string
  quizzesTaken: number
  questionsAnswered: number
  correct: number
}

export interface WeakTerm {
  key: string
  label: string
  correct: number
  answered: number
  projectId: string | null
  sourceId: string | null
}

export interface QuizAnalytics {
  accuracy: number | null
  questionsAnswered: number
  quizzesTaken: number
  batches: BatchAccuracy[]
  needsWork: WeakTerm[]
  recent: QuizResult[]
}

export function resultBatchKey(result: Pick<QuizResult, 'knowledge_project_id'>): string {
  return result.knowledge_project_id ?? 'unassigned'
}

export function accuracyPercent(correct: number, answered: number): number | null {
  if (answered <= 0) return null
  return Math.round((correct / answered) * 100)
}

export function summarizeQuizResults(
  results: QuizResult[],
  { batchKey, wikiLabels }: { batchKey: string; wikiLabels: Map<string, string> },
): QuizAnalytics {
  const filtered = batchKey === ALL_BATCHES ? results : results.filter((result) => resultBatchKey(result) === batchKey)
  const recent = [...filtered].sort((a, b) => b.completed_at.localeCompare(a.completed_at))
  const questionsAnswered = recent.reduce((sum, result) => sum + result.question_count, 0)
  const correct = recent.reduce((sum, result) => sum + result.correct_count, 0)

  return {
    accuracy: accuracyPercent(correct, questionsAnswered),
    questionsAnswered,
    quizzesTaken: recent.length,
    batches: batchAccuracies(recent),
    needsWork: weakTerms(recent, wikiLabels),
    recent,
  }
}

function batchAccuracies(results: QuizResult[]): BatchAccuracy[] {
  const groups = new Map<string, BatchAccuracy>()
  for (const result of results) {
    const key = resultBatchKey(result)
    const existing = groups.get(key)
    if (!existing) {
      groups.set(key, {
        key,
        title: result.title,
        quizzesTaken: 1,
        questionsAnswered: result.question_count,
        correct: result.correct_count,
      })
      continue
    }
    existing.quizzesTaken += 1
    existing.questionsAnswered += result.question_count
    existing.correct += result.correct_count
  }
  return [...groups.values()].sort((a, b) => {
    const rank = (a.title === 'Unassigned' ? 1 : 0) - (b.title === 'Unassigned' ? 1 : 0)
    return rank || a.title.localeCompare(b.title)
  })
}

function weakTerms(results: QuizResult[], wikiLabels: Map<string, string>): WeakTerm[] {
  const groups = new Map<string, WeakTerm & { latestMiss: string }>()
  for (const result of results) {
    for (const answer of result.answers) {
      const key = answer.wiki_id ?? `stem:${answer.question}`
      const label = (answer.wiki_id && wikiLabels.get(answer.wiki_id)) || answer.question
      const existing = groups.get(key)
      if (!existing) {
        groups.set(key, {
          key,
          label,
          correct: answer.correct ? 1 : 0,
          answered: 1,
          projectId: answer.correct ? null : result.knowledge_project_id,
          sourceId: answer.correct ? null : result.source_id,
          latestMiss: answer.correct ? '' : result.completed_at,
        })
        continue
      }
      existing.correct += answer.correct ? 1 : 0
      existing.answered += 1
      if (!answer.correct && result.completed_at >= existing.latestMiss) {
        existing.projectId = result.knowledge_project_id
        existing.sourceId = result.source_id
        existing.latestMiss = result.completed_at
      }
    }
  }
  return [...groups.values()]
    .filter((term) => term.correct < term.answered)
    .sort((a, b) => {
      const accuracy = a.correct / a.answered - b.correct / b.answered
      if (accuracy !== 0) return accuracy
      return b.answered - b.correct - (a.answered - a.correct)
    })
    .slice(0, NEEDS_WORK_CAP)
    .map((term) => ({
      key: term.key,
      label: term.label,
      correct: term.correct,
      answered: term.answered,
      projectId: term.projectId,
      sourceId: term.sourceId,
    }))
}
