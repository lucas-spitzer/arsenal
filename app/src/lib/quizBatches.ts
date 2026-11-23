import { isWikiTermQuiz } from './assessmentOrigin'

const UNASSIGNED = 'Unassigned'

export interface QuizBatchInput {
  source_id?: string | null
  lesson_id?: string | null
  knowledge_project_id?: string | null
  created_at: string
  origin?: Record<string, unknown> | null
}

export interface QuizBatchTitle {
  id: string
  title: string
}

export interface QuizBatch {
  key: string
  sourceKey: string
  sourceId: string | null
  lessonId: string | null
  projectId: string | null
  title: string
  sourceName: string
  questionCount: number
  newestAt: string
}

export function quizBatchKey(sourceId: string | null, projectId: string | null): string {
  return projectId ?? `unassigned:${sourceId ?? ''}`
}

export function listQuizBatches(
  quizzes: QuizBatchInput[],
  titles: QuizBatchTitle[],
  sourceName: (homeId: string | null) => string,
): QuizBatch[] {
  const titleById = new Map(titles.map((title) => [title.id, title.title]))
  const groups = new Map<string, QuizBatchInput[]>()
  for (const quiz of quizzes) {
    // Wiki-term questions practice on the Flashcards tab only.
    if (isWikiTermQuiz(quiz)) continue
    const home = batchHome(quiz)
    const projectId = quiz.knowledge_project_id ?? null
    const key = quizBatchKey(home.sourceKey, projectId)
    groups.set(key, [...(groups.get(key) ?? []), quiz])
  }

  const batches = [...groups.entries()].flatMap(([key, rows]) => {
    const first = rows[0]
    if (!first) return []
    const home = batchHome(first)
    const projectId = first.knowledge_project_id ?? null
    const newestAt = rows.reduce((latest, row) => (row.created_at > latest ? row.created_at : latest), '')
    return [{
      key,
      sourceKey: home.sourceKey,
      sourceId: home.sourceId,
      lessonId: home.lessonId,
      projectId,
      title: projectId ? (titleById.get(projectId) ?? 'Untitled batch') : UNASSIGNED,
      sourceName: sourceName(home.lessonId ?? home.sourceId),
      questionCount: rows.length,
      newestAt,
    }]
  })

  return batches.sort((a, b) => {
    const rank = sourceRank(a.sourceName) - sourceRank(b.sourceName)
    if (rank !== 0) return rank
    const name = a.sourceName.localeCompare(b.sourceName)
    if (name !== 0) return name
    return b.newestAt.localeCompare(a.newestAt)
  })
}

export function quizBatchSources(batches: QuizBatch[]): { sourceKey: string; sourceName: string }[] {
  const names = new Map<string, string>()
  for (const batch of batches) names.set(batch.sourceKey, batch.sourceName)
  return [...names.entries()]
    .map(([sourceKey, sourceName]) => ({ sourceKey, sourceName }))
    .sort((a, b) => sourceRank(a.sourceName) - sourceRank(b.sourceName) || a.sourceName.localeCompare(b.sourceName))
}

export function batchesForSource(batches: QuizBatch[], sourceKey: string): QuizBatch[] {
  return batches
    .filter((batch) => batch.sourceKey === sourceKey)
    .sort((a, b) => b.newestAt.localeCompare(a.newestAt))
}

export function defaultQuizBatch(
  batches: QuizBatch[],
  hint: { sourceId?: string | null; projectId?: string | null; batchKey?: string | null },
): QuizBatch | null {
  if (hint.batchKey) {
    const keyed = batches.find((batch) => batch.key === hint.batchKey)
    if (keyed) return keyed
  }
  if (hint.projectId) {
    const project = batches.find(
      (batch) => batch.projectId === hint.projectId && (hint.sourceId == null || batch.sourceKey === hint.sourceId),
    )
    if (project) return project
  }
  const pool = hint.sourceId ? batches.filter((batch) => batch.sourceKey === hint.sourceId) : batches
  return newestNamedBatch(pool)
}

function batchHome(quiz: QuizBatchInput): { sourceId: string | null; lessonId: string | null; sourceKey: string } {
  const lessonId = quiz.lesson_id ?? null
  if (lessonId) return { sourceId: null, lessonId, sourceKey: lessonId }
  const sourceId = quiz.source_id ?? null
  return { sourceId, lessonId: null, sourceKey: sourceId ?? '' }
}

function newestNamedBatch(batches: QuizBatch[]): QuizBatch | null {
  if (batches.length === 0) return null
  const named = batches.filter((batch) => batch.projectId)
  const candidates = named.length > 0 ? named : batches
  return [...candidates].sort((a, b) => b.newestAt.localeCompare(a.newestAt))[0] ?? null
}

function sourceRank(name: string): number {
  return name === UNASSIGNED ? 1 : 0
}
