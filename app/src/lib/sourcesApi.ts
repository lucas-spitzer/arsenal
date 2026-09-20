import { apiRequest } from './apiClient'

export interface NdrSegment {
  id: string
  source_id: string
  workspace_id: string
  sequence_index: number
  kind: 'heading' | 'paragraph' | 'list_item' | 'table' | 'caption'
  text: string
  md?: string | null
  locator: Record<string, unknown>
  created_at: string
}

export interface ChapterSection {
  title: string
  level: number
  sequence_index: number
  heading_segment_id: string
  segment_ids: string[]
}

export interface DocumentChapter {
  id: string
  source_id: string
  workspace_id: string
  sequence_index: number
  title: string
  level: number
  segment_ids: string[]
  sections: ChapterSection[]
  created_at: string
}

// Fetch every segment for a source, paging past the endpoint's 1000-row cap.
export async function listAllSourceSegments(
  workspaceId: string,
  sourceId: string,
): Promise<NdrSegment[]> {
  const pageSize = 1000
  const all: NdrSegment[] = []
  for (let offset = 0; ; offset += pageSize) {
    const page = await apiRequest<NdrSegment[]>(
      `/workspaces/${workspaceId}/sources/${sourceId}/segments?limit=${pageSize}&offset=${offset}`,
    )
    all.push(...page)
    if (page.length < pageSize) return all
  }
}

export async function listSourceChapters(
  workspaceId: string,
  sourceId: string,
): Promise<DocumentChapter[]> {
  return apiRequest<DocumentChapter[]>(
    `/workspaces/${workspaceId}/sources/${sourceId}/chapters`,
  )
}

// Synthesized narration: one row per paragraph, usually sharing a chapter MP3,
// with word-level timings ({i, w, s, e} — word index, word, start/end seconds
// on that shared clip).
export interface NarrationWord {
  i: number
  w: string
  s: number
  e: number
  cs?: number
  ce?: number
}

export interface NarrationSegment {
  id: string
  source_id: string
  workspace_id: string
  chapter_id: string | null
  segment_id: string
  provider: string
  voice_id: string
  model_id: string
  text_hash: string
  duration_seconds: number
  audio_path?: string | null
  words: NarrationWord[]
  alignment_source: 'provider' | 'forced' | 'estimated'
  alignment_quality: Record<string, unknown>
  created_at: string
}

export interface NarrationAudio {
  narration_id: string
  segment_id: string
  audio_url: string
  expires_in: number
}

export async function listSourceNarration(
  workspaceId: string,
  sourceId: string,
): Promise<NarrationSegment[]> {
  const pageSize = 2000
  const all: NarrationSegment[] = []
  for (let offset = 0; ; offset += pageSize) {
    const page = await apiRequest<NarrationSegment[]>(
      `/workspaces/${workspaceId}/sources/${sourceId}/narration?limit=${pageSize}&offset=${offset}`,
    )
    all.push(...page)
    if (page.length < pageSize) return all
  }
}

export async function getNarrationAudioUrl(
  workspaceId: string,
  sourceId: string,
  narrationId: string,
): Promise<NarrationAudio> {
  return apiRequest<NarrationAudio>(
    `/workspaces/${workspaceId}/sources/${sourceId}/narration/${narrationId}/audio`,
  )
}
