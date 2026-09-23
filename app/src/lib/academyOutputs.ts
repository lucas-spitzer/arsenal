import { useMemo } from 'react'
import { useWorkspaceData } from '../features/workspace/workspaceDataContext'
import type { AcademyPage } from '../components/academy/types'
import { collapseDuplicateNarrationArtifacts } from './foundryMappers'
import { formatDuration } from './foundryFormat'
import { sourceDisplayName } from './sourceDisplay'
import type { Artifact, Source, WikiEntry } from './workspaceApi'

export type OutputKind = 'artifact' | 'flashcard' | 'question' | 'scenario' | 'wiki'
export type OutputType = 'all' | OutputKind
export type OutputSort = 'source' | 'newest' | 'difficulty' | 'type'

const UNASSIGNED = 'Unassigned'

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
  isNarration: boolean
}

export function isIncompleteNarrationArtifact(artifact: {
  artifact_type: string
  manifest: Record<string, unknown>
}): boolean {
  return (
    artifact.artifact_type === 'narration_audio'
    && artifact.manifest.status === 'in_progress'
  )
}
const AUDIO_FORMATS = new Set(['mp3', 'wav', 'm4a', 'ogg'])
const DIFFICULTY_ORDER: Record<string, number> = { easy: 0, medium: 1, hard: 2 }
const KIND_CHIP: Record<Exclude<OutputKind, 'artifact'>, string> = {
  flashcard: 'Flashcard',
  question: 'Question',
  scenario: 'Scenario',
  wiki: 'Wiki',
}

function difficultyRank(difficulty: string): number {
  return DIFFICULTY_ORDER[difficulty] ?? 9
}

function countLabel(value: unknown, unit: string): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return ''
  const rounded = Math.round(n)
  return `${rounded} ${unit}${rounded === 1 ? '' : 's'}`
}

function displayVoice(voiceId: string): string | null {
  const trimmed = voiceId.trim()
  if (!/^[A-Za-z][A-Za-z0-9 _-]{0,31}$/.test(trimmed)) return null
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

function narrationInstanceTitle(manifest: Record<string, unknown>): string {
  const parts: string[] = []
  const voice = displayVoice(String(manifest.voice_id ?? ''))
  if (voice) parts.push(voice)
  const seconds = Number(manifest.total_duration_seconds)
  if (Number.isFinite(seconds) && seconds > 0) {
    parts.push(formatDuration(Math.round(seconds)))
  }
  return parts.join(' · ')
}

export function artifactLibraryCard(artifact: Pick<
  Artifact,
  'artifact_type' | 'format' | 'manifest'
>): {
  chipLabel: string
  title: string
  isAudio: boolean
  isEbook: boolean
  isStudySheet: boolean
  isNarration: boolean
} {
  const format = (artifact.format || '').toLowerCase()
  const isNarration = artifact.artifact_type === 'narration_audio'
  const isAudio =
    !isNarration &&
    (artifact.artifact_type.includes('audio') || AUDIO_FORMATS.has(format))
  const isEbook =
    artifact.artifact_type === 'electronic_book' || format.startsWith('epub')
  const isStudySheet = artifact.artifact_type === 'study_sheet'

  let chipLabel = 'Artifact'
  let title = ''
  if (isNarration) {
    chipLabel = 'Audio'
    title = narrationInstanceTitle(artifact.manifest)
  } else if (isAudio) {
    chipLabel = 'Audio'
    title = narrationInstanceTitle(artifact.manifest)
  } else if (isEbook) {
    chipLabel = 'Book'
    title = countLabel(artifact.manifest.chapter_count, 'chapter')
  } else if (isStudySheet) {
    chipLabel = 'Sheet'
    title = countLabel(artifact.manifest.page_count, 'page')
  }

  return { chipLabel, title, isAudio, isEbook, isStudySheet, isNarration }
}

export function outputChipLabel(item: OutputItem): string {
  if (item.kind !== 'artifact') return KIND_CHIP[item.kind]
  if (item.isEbook) return 'Book'
  if (item.isStudySheet) return 'Sheet'
  if (item.isNarration || item.isAudio) return 'Audio'
  return 'Artifact'
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
        isNarration: false,
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
        isNarration: false,
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
        isNarration: false,
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
        isNarration: false,
      })),
      ...wikiEntriesToOutputItems(wikiEntries, nameOf),
      ...collapseDuplicateNarrationArtifacts(artifacts)
        .filter((a) => !isIncompleteNarrationArtifact(a))
        .map<OutputItem>((a) => {
        const card = artifactLibraryCard(a)
        return {
          kind: 'artifact',
          id: a.id,
          title: card.title,
          sourceId: a.source_id ?? null,
          sourceName: nameOf(a.source_id),
          badge: (a.format || 'file').toUpperCase(),
          createdAt: a.created_at,
          runnerPage: null,
          isAudio: card.isAudio,
          isEbook: card.isEbook,
          isStudySheet: card.isStudySheet,
          isNarration: card.isNarration,
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
    if (q) {
      const haystack = `${item.title} ${item.sourceName} ${outputChipLabel(item)}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
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
