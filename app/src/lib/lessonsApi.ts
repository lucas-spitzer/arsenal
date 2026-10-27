import { apiRequest, apiRequestVoid } from './apiClient'

// Academy ELO tab. Separate from wiki entries with entry_kind 'elo' (Knowledge runs).

export type LessonResourceKind = 'file' | 'link'
export type LessonIndexStatus = 'pending' | 'indexing' | 'ready' | 'failed' | 'skipped'

export interface LessonObjective {
  id: string
  lesson_id: string
  position: number
  text: string
  code: string | null
  is_async: boolean
}

export interface LessonResource {
  id: string
  lesson_id: string
  kind: LessonResourceKind
  label: string
  position: number
  url: string | null
  filename: string | null
  mime_type: string | null
  file_size_bytes: number | null
  index_status: LessonIndexStatus
  index_error: string | null
  created_at: string
  updated_at: string
}

export interface Lesson {
  id: string
  workspace_id: string
  title: string
  sort_order: number
  notes: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  objectives: LessonObjective[]
  resources: LessonResource[]
}

export interface LessonObjectiveInput {
  text: string
  code: string | null
  is_async: boolean
}

export interface LessonInput {
  title: string
  sort_order?: number | null
  notes?: string | null
}

const base = (workspaceId: string) => `/workspaces/${workspaceId}/lessons`

export async function listLessons(workspaceId: string): Promise<Lesson[]> {
  return apiRequest<Lesson[]>(base(workspaceId))
}

export async function createLesson(
  workspaceId: string,
  payload: LessonInput & { objectives: LessonObjectiveInput[] },
): Promise<Lesson> {
  return apiRequest<Lesson>(base(workspaceId), { method: 'POST', body: JSON.stringify(payload) })
}

export async function updateLesson(
  workspaceId: string,
  lessonId: string,
  payload: Partial<LessonInput>,
): Promise<Lesson> {
  return apiRequest<Lesson>(`${base(workspaceId)}/${lessonId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteLesson(workspaceId: string, lessonId: string): Promise<void> {
  await apiRequestVoid(`${base(workspaceId)}/${lessonId}`, { method: 'DELETE' })
}

export async function replaceLessonObjectives(
  workspaceId: string,
  lessonId: string,
  objectives: LessonObjectiveInput[],
): Promise<Lesson> {
  return apiRequest<Lesson>(`${base(workspaceId)}/${lessonId}/objectives`, {
    method: 'PUT',
    body: JSON.stringify({ objectives }),
  })
}

export async function uploadLessonFiles(
  workspaceId: string,
  lessonId: string,
  files: File[],
): Promise<LessonResource[]> {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  return apiRequest<LessonResource[]>(`${base(workspaceId)}/${lessonId}/resources/files`, {
    method: 'POST',
    body,
  })
}

export async function addLessonLink(
  workspaceId: string,
  lessonId: string,
  payload: { label: string; url: string },
): Promise<LessonResource> {
  return apiRequest<LessonResource>(`${base(workspaceId)}/${lessonId}/resources/links`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteLessonResource(
  workspaceId: string,
  lessonId: string,
  resourceId: string,
): Promise<void> {
  await apiRequestVoid(`${base(workspaceId)}/${lessonId}/resources/${resourceId}`, {
    method: 'DELETE',
  })
}

export async function reindexLessonResource(
  workspaceId: string,
  lessonId: string,
  resourceId: string,
): Promise<LessonResource> {
  return apiRequest<LessonResource>(
    `${base(workspaceId)}/${lessonId}/resources/${resourceId}/reindex`,
    { method: 'POST' },
  )
}

export async function reindexAllLessons(
  workspaceId: string,
): Promise<{ lessons: number; files: number }> {
  return apiRequest<{ lessons: number; files: number }>(`${base(workspaceId)}/reindex`, {
    method: 'POST',
  })
}

export async function lessonResourceUrl(
  workspaceId: string,
  lessonId: string,
  resourceId: string,
): Promise<string> {
  const { url } = await apiRequest<{ url: string }>(
    `${base(workspaceId)}/${lessonId}/resources/${resourceId}/download`,
  )
  return url
}
