import { getAccessToken } from '../features/auth/authService'
import { ApiError, apiRequest, hasApiBaseUrl, parseApiErrorMessage } from './apiClient'
import type { AnswerPool } from './answerPool'
import type { AssessmentVisual } from './workspaceApi'

export type KnowledgeStatus = 'structuring' | 'composing' | 'drafting' | 'ready' | 'failed'
export type ItemKind = 'question' | 'scenario'

export interface KnowledgeProjectSummary {
  id: string
  workspace_id: string
  source_id: string
  title: string
  status: KnowledgeStatus
  error: string | null
  notes_filename: string | null
  draft_questions: boolean
  draft_scenarios: boolean
  batch_instructions: Record<string, string>
  structure_run_id: string | null
  draft_run_id: string | null
  visual_run_id: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeFlashcard {
  assessment_id: string
  front: string
  back: string
}

export interface KnowledgeQuestion {
  plan_id: string
  assessment_id: string
  question: string
  subtype: string
  question_type: string
  options: string[]
  correct_answer: string
  answer_pool: AnswerPool | Record<string, never>
  bloom_level: string | null
  explanation: string | null
  difficulty: string
  draft: Record<string, unknown> | null
}

export interface KnowledgeScenario {
  plan_id: string
  assessment_id: string
  title: string
  prompt: string
  context: string | null
  evaluation_criteria: string[]
  subtype: string
  bloom_level: string | null
  difficulty: string
  draft: Record<string, unknown> | null
}

export interface KnowledgeEntry {
  wiki_entry_id: string
  preferred_label: string
  definition: string
  significance: string | null
  category: string | null
  items: { name: string; details: string }[]
  entry_kind: string
  importance: string
  plan_id: string
  enabled: boolean
  layout: string
  instructions: string
  visual: AssessmentVisual | null
  flashcard: KnowledgeFlashcard | null
  questions: KnowledgeQuestion[]
  scenarios: KnowledgeScenario[]
}

export interface KnowledgeDraftItem {
  plan_id: string
  item_type: 'flashcard' | 'question' | 'scenario'
  assessment_id: string | null
  title: string
  body: string
  visual: AssessmentVisual | null
}

export interface PipelineStep {
  step: string
  status: string
  detail?: string
}

export interface KnowledgeProjectDetail extends KnowledgeProjectSummary {
  pipeline: PipelineStep[]
  entries: KnowledgeEntry[]
  items: KnowledgeDraftItem[]
}

export interface BatchInput {
  kind: ItemKind
  category: string
  format: string
  instructions: string
  per_entry: number
  bloom_level: string
  mode: 'append' | 'replace'
}

export interface VariantsInput {
  kind: ItemKind
  wiki_entry_id: string
  format: string
  count: number
  mix: 'same' | 'spread'
  bloom_level: string
  instructions: string
}

export interface QuestionSave {
  question: string
  format: string
  answer_pool: AnswerPool
  explanation: string | null
  difficulty: string
  bloom_level: string | null
}

export interface ScenarioSave {
  title: string
  prompt: string
  context: string | null
  evaluation_criteria: string[]
  format: string
  difficulty: string
  bloom_level: string | null
}

export function activeKnowledgeRunId(project: KnowledgeProjectSummary): string | null {
  if (project.status === 'structuring') return project.structure_run_id
  if (project.status === 'drafting') return project.visual_run_id ?? project.draft_run_id
  return project.visual_run_id ?? project.draft_run_id ?? project.structure_run_id
}

async function postForm<TResponse>(path: string, form: FormData): Promise<TResponse> {
  if (!hasApiBaseUrl()) throw new ApiError('Missing VITE_API_BASE_URL.', 0)
  const token = await getAccessToken()
  if (!token) throw new ApiError('Missing access token.', 401)
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!response.ok) throw new ApiError(await parseApiErrorMessage(response), response.status)
  return response.json() as Promise<TResponse>
}

function json<TResponse>(path: string, method: string, body?: unknown): Promise<TResponse> {
  return apiRequest(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
}

export function listKnowledgeProjects(workspaceId: string): Promise<KnowledgeProjectSummary[]> {
  return apiRequest(`/workspaces/${workspaceId}/knowledge-projects`)
}

export function getKnowledgeProject(projectId: string): Promise<KnowledgeProjectDetail> {
  return apiRequest(`/knowledge-projects/${projectId}`)
}

export function createKnowledgeProject(
  workspaceId: string,
  input: { title: string; sourceId: string; notes: string; file: File | null },
): Promise<KnowledgeProjectDetail> {
  const form = new FormData()
  form.set('title', input.title)
  form.set('source_id', input.sourceId)
  form.set('raw_notes', input.file ? '' : input.notes)
  if (input.file) form.set('file', input.file)
  return postForm(`/workspaces/${workspaceId}/knowledge-projects`, form)
}

export function updateKnowledgeProject(
  projectId: string,
  input: { draft_questions?: boolean; draft_scenarios?: boolean; batch_instructions?: Record<string, string> },
): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}`, 'PATCH', input)
}

export function updateKnowledgePlan(
  projectId: string,
  planId: string,
  input: {
    enabled?: boolean
    layout?: string
    instructions?: string
    draft?: Record<string, unknown>
    clear_draft?: boolean
  },
): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}`, 'PATCH', input)
}

export function makeKnowledgeFlashcards(projectId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/flashcards`, 'POST')
}

export function generateKnowledgeBatch(projectId: string, input: BatchInput): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/batches`, 'POST', input)
}

export function generateKnowledgeVariants(projectId: string, input: VariantsInput): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/variants`, 'POST', input)
}

export function saveKnowledgeQuestion(
  projectId: string,
  planId: string,
  input: QuestionSave,
): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}/question`, 'PUT', input)
}

export function saveKnowledgeScenario(
  projectId: string,
  planId: string,
  input: ScenarioSave,
): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}/scenario`, 'PUT', input)
}

export function saveKnowledgeFlashcard(
  projectId: string,
  planId: string,
  input: { front: string; back: string },
): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}/flashcard`, 'PUT', input)
}

export function duplicateKnowledgeItem(projectId: string, planId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}/duplicate`, 'POST')
}

export function deleteKnowledgeItem(projectId: string, planId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}`, 'DELETE')
}

export function uploadPlanVisual(
  projectId: string,
  planId: string,
  input: { file: File; kind: string; placement: string; alt: string },
): Promise<KnowledgeProjectDetail> {
  const form = new FormData()
  form.set('file', input.file)
  form.set('kind', input.kind)
  form.set('placement', input.placement)
  form.set('alt', input.alt)
  return postForm(`/knowledge-projects/${projectId}/plans/${planId}/visual`, form)
}

export function deletePlanVisual(projectId: string, planId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/plans/${planId}/visual`, 'DELETE')
}

export function draftKnowledgeProject(projectId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/draft`, 'POST')
}

export function attachKnowledgeVisuals(projectId: string): Promise<KnowledgeProjectDetail> {
  return json(`/knowledge-projects/${projectId}/visuals`, 'POST')
}
