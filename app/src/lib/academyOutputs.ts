import { useMemo } from 'react'
import { useWorkspaceData } from '../features/workspace/workspaceDataContext'
import type { AcademyPage } from '../components/academy/types'
import { sourceDisplayName } from './sourceDisplay'
import type { Source, WikiEntry } from './workspaceApi'

export type OutputKind = 'artifact' | 'flashcard' | 'question' | 'scenario' | 'wiki'
export type OutputType = 'all' | OutputKind
export type OutputSort = 'source' | 'newest' | 'difficulty' | 'type'

export interface OutputItem {
  kind: OutputKind
  id: string
  title: string
  sourceId: string | null
  sourceName: string
  badge: string // difficulty for assessments, format for artifacts
  createdAt: string
  runnerPage: AcademyPage | null // where "Open" routes; null = artifact (reader/download)
  isAudio: boolean
  isEbook: boolean
  isStudySheet: boolean
}

const UNASSIGNED = 'Unassigned'
const AUDIO_FORMATS = new Set(['mp3', 'wav', 'm4a', 'ogg'])
const DIFFICULTY_ORDER: Record<string, number> = { easy: 0, medium: 1, hard: 2 }

function difficultyRank(difficulty: string): number {
  return DIFFICULTY_ORDER[difficulty] ?? 9
}

function sourceLabel(source: Source | undefined): string {
  if (!source) return UNASSIGNED
  return sourceDisplayName(source)
}

export function wikiSourceId(entry: WikiEntry): string | null {
  const origin = entry.origin
  if (origin && typeof origin.source_id === 'string' && origin.source_id.trim()) {
    return origin.source_id
  }
  const evidence = entry.evidence[0]
  return typeof evidence?.source_id === 'string' && evidence.source_id
    ? evidence.source_id
    : null
}

export function wikiEntriesToOutputItems(
  wikiEntries: WikiEntry[],
  nameOf: (id: string | null | undefined) => string,
): OutputItem[] {
  return wikiEntries
    .filter((entry) => entry.status !== 'deprecated')
    .map((entry) => {
      const sourceId = wikiSourceId(entry)
      return {
        kind: 'wiki',
        id: entry.id,
        title: entry.preferred_label,
        sourceId,
        sourceName: nameOf(sourceId),
        badge: entry.entry_kind || entry.importance,
        createdAt: entry.created_at,
        runnerPage: 'wiki',
        isAudio: false,
        isEbook: false,
        isStudySheet: false,
      }
    })
}

export function useOutputs(): { items: OutputItem[]; sources: { id: string; name: string }[] } {
  const { flashcards, quizzes, scenarios, artifacts, wikiEntries, sources } = useWorkspaceData()

  return useMemo(() => {
    const byId = new Map(sources.map((s) => [s.id, s]))
    const nameOf = (id: string | null | undefined) =>
      id ? sourceLabel(byId.get(id)) : UNASSIGNED

    const items: OutputItem[] = [
      ...flashcards.map<OutputItem>((f) => ({
        kind: 'flashcard',
        id: f.id,
        title: f.front,
        sourceId: f.source_id ?? null,
        sourceName: nameOf(f.source_id),
        badge: f.difficulty,
        createdAt: f.created_at,
        runnerPage: 'flashcards',
        isAudio: false,
        isEbook: false,
        isStudySheet: false,
      })),
      ...quizzes.map<OutputItem>((q) => ({
        kind: 'question',
        id: q.id,
        title: q.question,
        sourceId: q.source_id ?? null,
        sourceName: nameOf(q.source_id),
        badge: q.difficulty,
        createdAt: q.created_at,
        runnerPage: 'quiz',
        isAudio: false,
        isEbook: false,
        isStudySheet: false,
      })),
      ...scenarios.map<OutputItem>((s) => ({
        kind: 'scenario',
        id: s.id,
        title: s.title,
        sourceId: s.source_id ?? null,
        sourceName: nameOf(s.source_id),
        badge: s.difficulty,
        createdAt: s.created_at,
        runnerPage: 'scenarios',
        isAudio: false,
        isEbook: false,
        isStudySheet: false,
      })),
      ...wikiEntriesToOutputItems(wikiEntries, nameOf),
      ...artifacts.map<OutputItem>((a) => {
        const format = (a.format || '').toLowerCase()
        // narration_audio is a JSON manifest; listen in the Reader (chapter MP3s).
        // Raw audio file formats still use Download when present.
        const isNarrationManifest = a.artifact_type === 'narration_audio'
        const isAudio =
          !isNarrationManifest &&
          (a.artifact_type.includes('audio') || AUDIO_FORMATS.has(format))
        const isEbook = a.artifact_type === 'electronic_book' || format.startsWith('epub')
        const isStudySheet = a.artifact_type === 'study_sheet'
        return {
          kind: 'artifact',
          id: a.id,
          title: String(
            (typeof a.manifest.title === 'string' && a.manifest.title) || a.filename,
          ),
          sourceId: a.source_id ?? null,
          sourceName: nameOf(a.source_id),
          badge: (a.format || 'file').toUpperCase(),
          createdAt: a.created_at,
          runnerPage: null,
          isAudio,
          isEbook,
          isStudySheet,
        }
      }),
    ]

    // Distinct sources that actually have outputs, sorted by name.
    const seen = new Map<string, string>()
    for (const item of items) {
      if (item.sourceId && !seen.has(item.sourceId)) seen.set(item.sourceId, item.sourceName)
    }
    const sourceList = [...seen.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name))

    return { items, sources: sourceList }
  }, [flashcards, quizzes, scenarios, artifacts, wikiEntries, sources])
}

export function filterOutputs(
  items: OutputItem[],
  { search, type, sourceId }: { search: string; type: OutputType; sourceId: string | null },
): OutputItem[] {
  const q = search.trim().toLowerCase()
  return items.filter((item) => {
    if (type !== 'all' && item.kind !== type) return false
    if (sourceId && item.sourceId !== sourceId) return false
    if (q && !item.title.toLowerCase().includes(q)) return false
    return true
  })
}

// Shared filter+sort for a runner's raw records (flashcards, quizzes, scenarios)
// so each runner gets the same source/search/sort behavior as the Library.
export function filterAndSortRecords<
  T extends { source_id?: string | null; created_at: string; difficulty: string },
>(
  records: T[],
  getText: (record: T) => string,
  { search, sourceId, sort }: { search: string; sourceId: string | null; sort: OutputSort },
): T[] {
  const q = search.trim().toLowerCase()
  const filtered = records.filter(
    (r) =>
      (!sourceId || (r.source_id ?? null) === sourceId) &&
      (!q || getText(r).toLowerCase().includes(q)),
  )
  switch (sort) {
    case 'newest':
      return [...filtered].sort((a, b) => b.created_at.localeCompare(a.created_at))
    case 'difficulty':
      return [...filtered].sort(
        (a, b) => difficultyRank(a.difficulty) - difficultyRank(b.difficulty),
      )
    case 'source':
    case 'type':
    default:
      return [...filtered].sort(
        (a, b) =>
          (a.source_id ?? '').localeCompare(b.source_id ?? '') ||
          b.created_at.localeCompare(a.created_at),
      )
  }
}

export function sortOutputs(items: OutputItem[], sort: OutputSort): OutputItem[] {
  const out = [...items]
  switch (sort) {
    case 'newest':
      return out.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    case 'difficulty':
      return out.sort(
        (a, b) => (DIFFICULTY_ORDER[a.badge] ?? 9) - (DIFFICULTY_ORDER[b.badge] ?? 9),
      )
    case 'type':
      return out.sort((a, b) => a.kind.localeCompare(b.kind))
    case 'source':
    default:
      return out.sort(
        (a, b) => a.sourceName.localeCompare(b.sourceName) || b.createdAt.localeCompare(a.createdAt),
      )
  }
}
