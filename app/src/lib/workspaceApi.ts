import { getAccessToken } from '../features/auth/authService'
import {
  ApiError,
  apiRequest,
  apiRequestVoid,
  hasApiBaseUrl,
  parseApiErrorMessage,
} from './apiClient'

export interface Workspace {
  id: string
  owner_id: string
  name: string
  slug: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Source {
  id: string
  workspace_id: string
  filename: string
  slug: string
  mime_type: string
  storage_path: string
  file_hash: string
  file_size_bytes: number
  source_metadata: Record<string, unknown>
  status: string
  created_at: string
  updated_at: string
}

export interface WikiEntry {
  id: string
  workspace_id: string
  preferred_label: string
  definition: string
  entry_kind: string
  importance: string
  status: string
  canonical_slug: string
  aliases: string[]
  prerequisites: string[]
  pronunciation: string | null
  evidence: {
    source_id?: string
    segment_id?: string | null
    sequence_index?: number | null
    page?: number | null
    reader_link?: string | null
  }[]
  origin: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Artifact {
  id: string
  workspace_id: string
  source_id: string | null
  production_run_id: string | null
  artifact_type: string
  format: string
  filename: string
  storage_path: string
  file_size_bytes: number
  manifest: Record<string, unknown>
  created_at: string
}

export interface Flashcard {
  id: string
  source_id?: string | null
  production_run_id?: string | null
  item_id?: string | null
  subtype?: string | null
  front: string
  back: string
  difficulty: string
  tags: string[]
  created_at: string
}

export interface Quiz {
  id: string
  source_id?: string | null
  production_run_id?: string | null
  item_id?: string | null
  subtype?: string | null
  question: string
  question_type: string
  options: string[]
  correct_answer: string
  explanation: string | null
  difficulty: string
  created_at: string
}

export interface Scenario {
  id: string
  source_id?: string | null
  production_run_id?: string | null
  item_id?: string | null
  subtype?: string | null
  title: string
  prompt: string
  context: string | null
  evaluation_criteria: string[]
  difficulty: string
  created_at: string
}

export interface PipelineStep {
  step: string
  type: string
  status: string
  module?: string
  stage_id?: string
  stage_run_id?: string
  detail?: string
}

export interface ProductionRun {
  id: string
  workspace_id: string
  source_ids: string[]
  target_artifacts: string[]
  pipeline: PipelineStep[]
  status: string
  error: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  cost_usd: number
}

export interface StageRun {
  id: string
  production_run_id: string
  workspace_id: string
  stage_id: string
  stage_version: string
  module: string
  status: string
  inputs: Record<string, unknown>
  output: Record<string, unknown> | null
  promoted: Record<string, unknown> | null
  model: string | null
  token_usage: Record<string, number> | null
  api_usage: Record<string, unknown> | null
  cost_usd: number
  error: string | null
  started_at: string | null
  completed_at: string | null
}

// Learning/export outputs; any combination may be generated.
export const ARTIFACT_OPTIONS = [
  { value: 'electronic_book', label: 'Electronic Book' },
  { value: 'narration_audio', label: 'Audio Narration' },
  { value: 'wiki_knowledge', label: 'Wiki Knowledge' },
  { value: 'wiki_json', label: 'Wiki Export' },
  { value: 'study_sheet', label: 'Study Sheet' },
] as const

// Assessment outputs are selected individually; any combination may be generated.
export const ASSESSMENT_ARTIFACT_OPTIONS = [
  { value: 'flashcards', label: 'Flashcards' },
  { value: 'quizzes', label: 'Quizzes' },
  { value: 'scenarios', label: 'Scenarios' },
] as const

export async function listWorkspaces(): Promise<Workspace[]> {
  return apiRequest<Workspace[]>('/workspaces')
}

export async function createWorkspace(name: string, description?: string): Promise<Workspace> {
  return apiRequest<Workspace>('/workspaces', {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  })
}

export async function listSources(workspaceId: string): Promise<Source[]> {
  return apiRequest<Source[]>(`/workspaces/${workspaceId}/sources`)
}

async function uploadMultipart<TResponse>(path: string, file: File): Promise<TResponse> {
  if (!hasApiBaseUrl()) {
    throw new ApiError('Missing VITE_API_BASE_URL.', 0)
  }

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string
  const token = await getAccessToken()

  if (!token) {
    throw new ApiError('Missing access token.', 401)
  }

  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const message = await parseApiErrorMessage(response)
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<TResponse>
}

export async function uploadSource(workspaceId: string, file: File): Promise<Source> {
  return uploadMultipart<Source>(`/workspaces/${workspaceId}/sources`, file)
}

export async function listWikiEntries(
  workspaceId: string,
  search?: string,
): Promise<WikiEntry[]> {
  const params = new URLSearchParams()
  if (search) {
    params.set('search', search)
  }
  const query = params.toString()
  return apiRequest<WikiEntry[]>(
    `/workspaces/${workspaceId}/wiki/entries${query ? `?${query}` : ''}`,
  )
}

export async function listArtifacts(workspaceId: string): Promise<Artifact[]> {
  return apiRequest<Artifact[]>(`/workspaces/${workspaceId}/artifacts`)
}

export async function uploadArtifact(workspaceId: string, file: File): Promise<Artifact> {
  return uploadMultipart<Artifact>(`/workspaces/${workspaceId}/artifacts`, file)
}

export async function getArtifactDownloadUrl(
  artifactId: string,
): Promise<{ download_url: string }> {
  return apiRequest<{ download_url: string; expires_in: number }>(
    `/artifacts/${artifactId}/download`,
  )
}

export async function listFlashcards(workspaceId: string): Promise<Flashcard[]> {
  return apiRequest<Flashcard[]>(`/workspaces/${workspaceId}/flashcards`)
}

export async function listQuizzes(workspaceId: string): Promise<Quiz[]> {
  return apiRequest<Quiz[]>(`/workspaces/${workspaceId}/quizzes`)
}

export async function listScenarios(workspaceId: string): Promise<Scenario[]> {
  return apiRequest<Scenario[]>(`/workspaces/${workspaceId}/scenarios`)
}

export async function listProductionRuns(workspaceId: string): Promise<ProductionRun[]> {
  return apiRequest<ProductionRun[]>(`/workspaces/${workspaceId}/production-runs`)
}

export async function createProductionRun(
  workspaceId: string,
  payload: { source_ids: string[]; target_artifacts: string[] },
): Promise<ProductionRun> {
  return apiRequest<ProductionRun>(`/workspaces/${workspaceId}/production-runs`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function listStageRuns(runId: string): Promise<StageRun[]> {
  return apiRequest<StageRun[]>(`/production-runs/${runId}/stage-runs`)
}

export interface CatalogModel {
  model: string
  provider: string
  display_name: string
  capability_tier: number
  supports_reasoning: boolean
  reasoning_modes: string[]
  context_window: number | null
  input_per_million: number | null
  output_per_million: number | null
}

export interface TtsVoice {
  id: string
  display_name: string
}

export interface TtsCatalogModel {
  model: string
  provider: string
  display_name: string
  default_voice_id: string
  voices: TtsVoice[]
  price_per_million: number | null
  capability_tier: number
}

export interface StageSetting {
  stage_action: string
  label: string
  provider: string
  model: string
  reasoning_effort: string | null
  reasoning_tokens: number | null
  voice_id: string | null
  is_overridden: boolean
  default_provider: string
  default_model: string
  default_voice_id: string | null
}

export async function getModelCatalog(): Promise<CatalogModel[]> {
  const response = await apiRequest<{ models: CatalogModel[] }>('/llm/catalog')
  return response.models
}

export async function getTtsCatalog(): Promise<TtsCatalogModel[]> {
  const response = await apiRequest<{ models: TtsCatalogModel[] }>('/tts/catalog')
  return response.models
}

export async function getStageSettings(workspaceId: string): Promise<StageSetting[]> {
  const response = await apiRequest<{ settings: StageSetting[] }>(
    `/workspaces/${workspaceId}/stage-settings`,
  )
  return response.settings
}

export async function putStageSetting(
  workspaceId: string,
  stageAction: string,
  payload: {
    provider: string
    model: string
    reasoning_effort?: string | null
    reasoning_tokens?: number | null
    voice_id?: string | null
  },
): Promise<StageSetting> {
  return apiRequest<StageSetting>(
    `/workspaces/${workspaceId}/stage-settings/${stageAction}`,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  )
}

export async function deleteStageSetting(
  workspaceId: string,
  stageAction: string,
): Promise<void> {
  await apiRequestVoid(`/workspaces/${workspaceId}/stage-settings/${stageAction}`, {
    method: 'DELETE',
  })
}
