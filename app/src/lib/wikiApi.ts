import { apiRequest } from './apiClient'
import type { WikiEntry } from './workspaceApi'

export type WikiIngestBatchStatus =
  | 'transcribing'
  | 'transcribed'
  | 'structuring'
  | 'draft'
  | 'committed'
  | 'discarded'
  | 'failed'

export interface WikiIngestAttachment {
  order: number
  filename: string
  mime_type: string
  storage_path: string
  byte_size: number
}

export interface WikiIngestBatch {
  id: string
  workspace_id: string
  source_id: string | null
  production_run_id: string | null
  title: string
  raw_notes: string
  chapter_hint: string | null
  status: WikiIngestBatchStatus
  attachments: WikiIngestAttachment[]
  transcription_error: string | null
  committed_entry_ids: string[]
  created_at: string
  updated_at: string
}

export interface WikiReviseProposal {
  definition: string
  preferred_label: string | null
  aliases: string[] | null
}

export async function createWikiKnowledge(
  workspaceId: string,
  payload: {
    notes: string
    source_id: string
    chapter_hint?: string | null
    title?: string | null
  },
): Promise<WikiIngestBatch> {
  return apiRequest<WikiIngestBatch>(`/workspaces/${workspaceId}/wiki/ingest-batches`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function createWikiKnowledgeFromFiles(
  workspaceId: string,
  payload: {
    source_id: string
    chapter_hint?: string | null
    title?: string | null
    files: File[]
  },
): Promise<WikiIngestBatch> {
  const form = new FormData()
  form.append('source_id', payload.source_id)
  if (payload.chapter_hint) {
    form.append('chapter_hint', payload.chapter_hint)
  }
  if (payload.title) {
    form.append('title', payload.title)
  }
  for (const file of payload.files) {
    form.append('files', file)
  }

  return apiRequest<WikiIngestBatch>(
    `/workspaces/${workspaceId}/wiki/ingest-batches/from-files`,
    {
      method: 'POST',
      body: form,
    },
  )
}

export async function reviseWikiEntry(
  workspaceId: string,
  entryId: string,
  instruction: string,
): Promise<WikiReviseProposal> {
  return apiRequest<WikiReviseProposal>(
    `/workspaces/${workspaceId}/wiki/entries/${entryId}/revise`,
    {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    },
  )
}

export async function updateWikiEntry(
  workspaceId: string,
  entryId: string,
  payload: Partial<{
    preferred_label: string
    definition: string
    entry_kind: string
    importance: string
    aliases: string[]
    pronunciation: string | null
  }>,
): Promise<WikiEntry> {
  return apiRequest<WikiEntry>(`/workspaces/${workspaceId}/wiki/entries/${entryId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function createWikiEntry(
  workspaceId: string,
  payload: {
    preferred_label: string
    definition: string
    entry_kind?: 'term' | 'concept' | 'insight'
    importance?: 'essential' | 'supporting' | 'contextual'
    aliases?: string[]
    pronunciation?: string | null
    origin?: Record<string, unknown>
  },
): Promise<WikiEntry> {
  return apiRequest<WikiEntry>(`/workspaces/${workspaceId}/wiki/entries`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deprecateWikiEntry(
  workspaceId: string,
  entryId: string,
): Promise<WikiEntry> {
  return apiRequest<WikiEntry>(`/workspaces/${workspaceId}/wiki/entries/${entryId}`, {
    method: 'DELETE',
  })
}
