import { apiRequest } from './apiClient'

export type QuizResultScope = 'one_per_term' | 'every_variant'

export interface QuizResultAnswer {
  quiz_id: string
  wiki_id: string | null
  question: string
  selected: string
  answer: string
  correct: boolean
}

export interface QuizResult {
  id: string
  workspace_id: string
  knowledge_project_id: string | null
  source_id: string | null
  title: string
  scope: QuizResultScope
  correct_count: number
  question_count: number
  answers: QuizResultAnswer[]
  completed_at: string
}

export interface QuizResultDraftAnswer {
  quiz_id: string
  question: string
  options: string[]
  selected_index: number
}

export interface QuizResultDraft {
  knowledge_project_id: string | null
  source_id: string | null
  scope: QuizResultScope
  answers: QuizResultDraftAnswer[]
}

export function listQuizResults(workspaceId: string): Promise<QuizResult[]> {
  return apiRequest<QuizResult[]>(`/workspaces/${workspaceId}/quiz-results`)
}

export function createQuizResult(workspaceId: string, draft: QuizResultDraft): Promise<QuizResult> {
  return apiRequest<QuizResult>(`/workspaces/${workspaceId}/quiz-results`, {
    method: 'POST',
    body: JSON.stringify(draft),
  })
}
