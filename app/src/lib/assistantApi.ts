import { apiRequest, apiRequestVoid } from './apiClient'

export type AssistantMode = 'discussion' | 'scenario'
export type DiscussionSubmode = 'socratic' | 'euclidean' | 'tbs'

export interface AssistantMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Citation {
  kind: 'segment' | 'wiki' | 'lesson'
  label: string
  snippet: string
  similarity: number
  reader_link: string | null
  locator: Record<string, unknown>
}

export interface ScenarioEvaluation {
  passed: boolean
  score: number | null
  feedback: string
  met_criteria: string[]
  missed_criteria: string[]
}

export interface AssistantChatResponse {
  answer: string
  grounded: boolean
  citations: Citation[]
  evaluation: ScenarioEvaluation | null
}

export interface AssistantChatRequest {
  mode: AssistantMode
  submode?: DiscussionSubmode
  messages: AssistantMessage[]
  source_ids?: string[]
  lesson_ids?: string[]
  scenario_id?: string
}

export async function assistantChat(
  workspaceId: string,
  request: AssistantChatRequest,
): Promise<AssistantChatResponse> {
  return apiRequest<AssistantChatResponse>(
    `/workspaces/${workspaceId}/assistant/chat`,
    { method: 'POST', body: JSON.stringify(request) },
  )
}

// --- Persisted discussion threads -----------------------------------------

export interface DiscussionThread {
  id: string
  workspace_id: string
  title: string
  submode: DiscussionSubmode
  source_id: string | null
  /** Academy ELO class this thread focuses on ("Discuss this class"). */
  lesson_id?: string | null
  created_at: string
  updated_at: string
}

export interface DiscussionMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  created_at: string
}

export interface DiscussionThreadDetail extends DiscussionThread {
  messages: DiscussionMessage[]
}

export interface CreateThreadRequest {
  title: string
  submode?: DiscussionSubmode
  source_id?: string | null
  lesson_id?: string | null
  seed_prompt?: string | null
}

export interface SendThreadMessageResponse {
  user_message: DiscussionMessage
  assistant_message: DiscussionMessage
  grounded: boolean
}

export async function listThreads(workspaceId: string): Promise<DiscussionThread[]> {
  return apiRequest<DiscussionThread[]>(`/workspaces/${workspaceId}/assistant/threads`)
}

export async function createThread(
  workspaceId: string,
  request: CreateThreadRequest,
): Promise<DiscussionThreadDetail> {
  return apiRequest<DiscussionThreadDetail>(
    `/workspaces/${workspaceId}/assistant/threads`,
    { method: 'POST', body: JSON.stringify(request) },
  )
}

export async function getThread(
  workspaceId: string,
  threadId: string,
): Promise<DiscussionThreadDetail> {
  return apiRequest<DiscussionThreadDetail>(
    `/workspaces/${workspaceId}/assistant/threads/${threadId}`,
  )
}

export async function updateThread(
  workspaceId: string,
  threadId: string,
  request: { title?: string; submode?: DiscussionSubmode },
): Promise<DiscussionThread> {
  return apiRequest<DiscussionThread>(
    `/workspaces/${workspaceId}/assistant/threads/${threadId}`,
    { method: 'PATCH', body: JSON.stringify(request) },
  )
}

export async function deleteThread(workspaceId: string, threadId: string): Promise<void> {
  await apiRequestVoid(
    `/workspaces/${workspaceId}/assistant/threads/${threadId}`,
    { method: 'DELETE' },
  )
}

export async function sendThreadMessage(
  workspaceId: string,
  threadId: string,
  content: string,
): Promise<SendThreadMessageResponse> {
  return apiRequest<SendThreadMessageResponse>(
    `/workspaces/${workspaceId}/assistant/threads/${threadId}/messages`,
    { method: 'POST', body: JSON.stringify({ content }) },
  )
}
