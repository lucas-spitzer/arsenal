import { useMemo } from 'react'
import { useWorkspaceData } from '../features/workspace/workspaceDataContext'
import type { AcademyPage } from '../components/academy/types'
import { collapseDuplicateNarrationArtifacts } from './foundryMappers'
import { formatDuration } from './foundryFormat'
import { sourceDisplayName } from './sourceDisplay'
import type { Artifact, KnowledgeRunTitle, Source, WikiEntry } from './workspaceApi'

export type OutputKind = 'audio' | 'book' | 'artifact' | 'material' | 'flashcard' | 'question' | 'scenario' | 'wiki'
export type NarrationDownloadState = 'ready' | 'preparing' | 'failed' | 'absent'
export type OutputType = 'all' | OutputKind
export type OutputSort = 'source' | 'newest' | 'difficulty' | 'type'

const UNASSIGNED = 'Unassigned'
export const STUDY_MATERIAL_GROUP = 'Study Material'

export interface OutputItem {
  kind: OutputKind
  id: string
  title: string
  sourceId: string | null
  sourceName: string
  /** Source title for a book, audio file, or wiki. Run title for a knowledge batch. Material title for study material. */
  footer: string
  badge: string // difficulty for assessments, format for artifacts
  createdAt: string
  runnerPage: AcademyPage | null // where "Open" routes; null = artifact (reader/download)
  isAudio: boolean
  isEbook: boolean
  isNarration: boolean
  /** Narration MP3 readiness. Null for every other library item. */
  narrationDownload: NarrationDownloadState | null
  /** Knowledge run this batch belongs to. Study opens only that run. */
  projectId: string | null
  /** Member text for a grouped card. Included in Library search only. */
  searchText?: string
}

// Same study-guide kinds the student Academy rail hides. Books, audio, study material, and wiki stay.
export const studentHiddenLibraryKinds = ['flashcard', 'question', 'scenario'] as const satisfies readonly OutputKind[]

const studentHiddenLibraryKindSet = new Set<OutputKind>(studentHiddenLibraryKinds)

export function libraryItemsForRole<T extends { kind: OutputKind }>(items: T[], isAdmin: boolean): T[] {
  if (isAdmin) return items
  return items.filter((item) => !studentHiddenLibraryKindSet.has(item.kind))
}

export function isStudentHiddenLibraryKind(kind: OutputKind): boolean {
  return studentHiddenLibraryKindSet.has(kind)
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
const KIND_CHIP: Record<OutputKind, string> = {
  audio: 'Audio',
  book: 'Book',
  artifact: 'Artifact',
  material: 'Material',
  flashcard: 'Flashcard',
  question: 'Question',
  scenario: 'Scenario',
  wiki: 'Wiki',
}

function difficultyRank(difficulty: string): number {
  return DIFFICULTY_ORDER[difficulty] ?? 9
}

function countLabel(value: unknown, unit: string, plural = `${unit}s`): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return ''
  const rounded = Math.round(n)
  return `${rounded} ${rounded === 1 ? unit : plural}`
}

function displayVoice(voiceId: string): string | null {
  const trimmed = voiceId.trim()
  if (!/^[A-Za-z][A-Za-z0-9 _-]{0,31}$/.test(trimmed)) return null
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

function durationTitle(manifest: Record<string, unknown>): string {
  const seconds = Number(manifest.total_duration_seconds)
  if (!Number.isFinite(seconds) || seconds <= 0) return ''
  return formatDuration(Math.round(seconds))
}

function narrationInstanceTitle(manifest: Record<string, unknown>): string {
  const parts: string[] = []
  const voice = displayVoice(String(manifest.voice_id ?? ''))
  if (voice) parts.push(voice)
  const duration = durationTitle(manifest)
  if (duration) parts.push(duration)
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
  isStudyMaterial: boolean
  isNarration: boolean
} {
  const format = (artifact.format || '').toLowerCase()
  const isNarration = artifact.artifact_type === 'narration_audio'
  const isAudio =
    !isNarration &&
    (artifact.artifact_type.includes('audio') || AUDIO_FORMATS.has(format))
  const isEbook =
    artifact.artifact_type === 'electronic_book' || format.startsWith('epub')
  const isStudyMaterial = isStudyMaterialArtifact(artifact)

  let chipLabel = 'Artifact'
  let title = ''
  if (isStudyMaterial) {
    chipLabel = 'Material'
    title = typeof artifact.manifest.title === 'string' ? artifact.manifest.title : ''
  } else if (isNarration) {
    chipLabel = 'Audio'
    title = durationTitle(artifact.manifest)
  } else if (isAudio) {
    chipLabel = 'Audio'
    title = narrationInstanceTitle(artifact.manifest)
  } else if (isEbook) {
    chipLabel = 'Book'
    title = countLabel(artifact.manifest.chapter_count, 'chapter')
  }

  return { chipLabel, title, isAudio, isEbook, isStudyMaterial, isNarration }
}

export function narrationDownloadState(
  manifest: Record<string, unknown>,
): NarrationDownloadState {
  const status = manifest.combined_audio_status
  const path = manifest.combined_audio_path
  if (status === 'preparing') return 'preparing'
  if (status === 'failed') return 'failed'
  if (typeof path === 'string' && path.length > 0) return 'ready'
  return 'absent'
}

export function isStudyMaterialArtifact(artifact: Pick<Artifact, 'artifact_type'>): boolean {
  return artifact.artifact_type === 'study_material'
}

export function outputChipLabel(item: OutputItem): string {
  return KIND_CHIP[item.kind]
}

/** Reader source when the rail opens with no book in the URL. */
export function defaultReaderSourceId({
  routeSourceId,
  focusedSourceId,
  books,
}: {
  routeSourceId: string | null
  focusedSourceId: string | null
  books: Pick<OutputItem, 'sourceId' | 'sourceName' | 'createdAt'>[]
}): string | null {
  if (routeSourceId) return routeSourceId
  const readable = books.flatMap((book) =>
    book.sourceId
      ? [{ sourceId: book.sourceId, sourceName: book.sourceName, createdAt: book.createdAt }]
      : [],
  )
  if (focusedSourceId && readable.some((book) => book.sourceId === focusedSourceId)) {
    return focusedSourceId
  }
  const first = [...readable].sort(
    (a, b) => a.sourceName.localeCompare(b.sourceName) || a.createdAt.localeCompare(b.createdAt),
  )[0]
  return first?.sourceId ?? null
}

const RUN_FOOTER_KINDS = new Set<OutputKind>(['flashcard', 'question', 'scenario', 'material'])

export function outputFooter(kind: OutputKind, sourceName: string, runTitle: string | null | undefined): string {
  const title = runTitle?.trim() ?? ''
  if (RUN_FOOTER_KINDS.has(kind) && title) return title
  return sourceName
}

function titleByProjectId(titles: KnowledgeRunTitle[]): Map<string, string> {
  return new Map(titles.map((run) => [run.id, run.title]))
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
  const groups = new Map<string, WikiEntry[]>()
  for (const entry of wikiEntries) {
    if (entry.status === 'deprecated') continue
    const sourceId = wikiSourceId(entry)
    const key = sourceId ?? ''
    const list = groups.get(key) ?? []
    list.push(entry)
    groups.set(key, list)
  }

  return [...groups.entries()].map(([key, entries]) => {
    const sourceId = key || null
    const sourceName = nameOf(sourceId)
    const newest = entries.reduce((latest, entry) =>
      entry.created_at > latest.created_at ? entry : latest,
    )
    return {
      kind: 'wiki',
      id: sourceId ?? 'unassigned',
      title: countLabel(entries.length, 'entry', 'entries'),
      sourceId,
      sourceName,
      footer: outputFooter('wiki', sourceName, null),
      badge: '',
      createdAt: newest.created_at,
      runnerPage: 'wiki',
      isAudio: false,
      isEbook: false,
      isNarration: false,
      narrationDownload: null,
      projectId: null,
      searchText: entries.map((entry) => entry.preferred_label).join(' '),
    }
  })
}

interface KnowledgeRecord {
  id: string
  source_id?: string | null
  knowledge_project_id?: string | null
  difficulty: string
  created_at: string
}

export function knowledgeRunOutputItems<T extends KnowledgeRecord>(
  records: T[],
  {
    kind,
    runnerPage,
    unit,
    plural,
    titleOf,
    searchOf,
    nameOf,
    projectTitle,
  }: {
    kind: 'flashcard' | 'question' | 'scenario'
    runnerPage: AcademyPage
    unit: string
    plural: string
    titleOf: (record: T) => string
    searchOf: (record: T) => string
    nameOf: (id: string | null | undefined) => string
    projectTitle: Map<string, string>
  },
): OutputItem[] {
  const grouped = new Map<string, T[]>()
  const loose: T[] = []
  for (const record of records) {
    const projectId = record.knowledge_project_id
    if (!projectId) {
      loose.push(record)
      continue
    }
    const list = grouped.get(projectId) ?? []
    list.push(record)
    grouped.set(projectId, list)
  }

  const batches = [...grouped.entries()].map(([projectId, batch]) => {
    const sourceId = batch.find((record) => record.source_id)?.source_id ?? null
    const sourceName = nameOf(sourceId)
    const newest = batch.reduce((latest, record) =>
      record.created_at > latest.created_at ? record : latest,
    )
    return {
      kind,
      id: projectId,
      projectId,
      title: countLabel(batch.length, unit, plural),
      sourceId,
      sourceName,
      footer: outputFooter(kind, sourceName, projectTitle.get(projectId) ?? null),
      badge: '',
      createdAt: newest.created_at,
      runnerPage,
      isAudio: false,
      isEbook: false,
      isNarration: false,
      narrationDownload: null,
      searchText: batch.map(searchOf).join(' '),
    } satisfies OutputItem
  })

  const singles = loose.map((record) => {
    const sourceName = nameOf(record.source_id)
    return {
      kind,
      id: record.id,
      projectId: null,
      title: titleOf(record),
      sourceId: record.source_id ?? null,
      sourceName,
      footer: outputFooter(kind, sourceName, null),
      badge: record.difficulty,
      createdAt: record.created_at,
      runnerPage,
      isAudio: false,
      isEbook: false,
      isNarration: false,
      narrationDownload: null,
    } satisfies OutputItem
  })

  return [...batches, ...singles]
}

export function useOutputs(): { items: OutputItem[]; sources: { id: string; name: string }[] } {
  const { flashcards, quizzes, scenarios, artifacts, wikiEntries, sources, knowledgeRunTitles } =
    useWorkspaceData()

  return useMemo(() => {
    const byId = new Map(sources.map((s) => [s.id, s]))
    const nameOf = (id: string | null | undefined) =>
      id ? sourceLabel(byId.get(id)) : UNASSIGNED
    const projectTitle = titleByProjectId(knowledgeRunTitles)

    const items: OutputItem[] = [
      ...knowledgeRunOutputItems(flashcards, {
        kind: 'flashcard',
        runnerPage: 'flashcards',
        unit: 'card',
        plural: 'cards',
        titleOf: (card) => card.front,
        searchOf: (card) => `${card.front} ${card.back}`,
        nameOf,
        projectTitle,
      }),
      ...knowledgeRunOutputItems(quizzes, {
        kind: 'question',
        runnerPage: 'quiz',
        unit: 'question',
        plural: 'questions',
        titleOf: (quiz) => quiz.question,
        searchOf: (quiz) => quiz.question,
        nameOf,
        projectTitle,
      }),
      ...knowledgeRunOutputItems(scenarios, {
        kind: 'scenario',
        runnerPage: 'scenarios',
        unit: 'scenario',
        plural: 'scenarios',
        titleOf: (scenario) => scenario.title,
        searchOf: (scenario) => `${scenario.title} ${scenario.prompt}`,
        nameOf,
        projectTitle,
      }),
      ...wikiEntriesToOutputItems(wikiEntries, nameOf),
      ...collapseDuplicateNarrationArtifacts(artifacts)
        .filter((a) => !isIncompleteNarrationArtifact(a))
        .map<OutputItem>((a) => {
        const card = artifactLibraryCard(a)
        const kind: OutputItem['kind'] = card.isStudyMaterial
          ? 'material'
          : card.isEbook
            ? 'book'
            : card.isAudio || card.isNarration
              ? 'audio'
              : 'artifact'
        const sourceName = card.isStudyMaterial ? STUDY_MATERIAL_GROUP : nameOf(a.source_id)
        const materialTitle = typeof a.manifest.title === 'string' ? a.manifest.title : ''
        return {
          kind,
          id: a.id,
          title: card.title,
          sourceId: a.source_id ?? null,
          sourceName,
          footer: outputFooter(kind, sourceName, card.isStudyMaterial ? materialTitle : null),
          badge: (a.format || 'file').toUpperCase(),
          createdAt: a.created_at,
          runnerPage: null,
          isAudio: card.isAudio,
          isEbook: card.isEbook,
          isNarration: card.isNarration,
          narrationDownload: card.isNarration ? narrationDownloadState(a.manifest) : null,
          projectId: null,
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
  }, [flashcards, quizzes, scenarios, artifacts, wikiEntries, sources, knowledgeRunTitles])
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
      const haystack = `${item.title} ${item.footer} ${item.sourceName} ${outputChipLabel(item)} ${item.searchText ?? ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })
}

// Shared filter+sort for a runner's raw records (flashcards, quizzes, scenarios)
// so each runner gets the same source/search/sort behavior as the Library.
export function filterAndSortRecords<
  T extends {
    source_id?: string | null
    knowledge_project_id?: string | null
    created_at: string
    difficulty: string
  },
>(
  records: T[],
  getText: (record: T) => string,
  {
    search,
    sourceId,
    sort,
    projectId = null,
  }: { search: string; sourceId: string | null; sort: OutputSort; projectId?: string | null },
): T[] {
  const q = search.trim().toLowerCase()
  const filtered = records.filter((record) => {
    const inScope = projectId
      ? (record.knowledge_project_id ?? null) === projectId
      : !sourceId || (record.source_id ?? null) === sourceId
    return inScope && (!q || getText(record).toLowerCase().includes(q))
  })
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
