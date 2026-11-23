import { useMemo } from 'react'
import type { AcademyPage } from '../components/academy/types'
import { useWorkspace } from '../features/workspace/workspaceContext'
import { useWorkspaceData } from '../features/workspace/workspaceDataContext'
import { isWikiTermQuiz } from './assessmentOrigin'
import { collapseDuplicateNarrationArtifacts } from './foundryMappers'
import { formatDuration, formatSpokenDuration } from './foundryFormat'
import type { Lesson } from './lessonsApi'
import { sourceDisplayName } from './sourceDisplay'
import { useLessons } from './useLessons'
import type { Artifact, Source, WikiEntry } from './workspaceApi'

export type OutputKind = 'audio' | 'book' | 'artifact' | 'material' | 'flashcard' | 'question' | 'scenario' | 'wiki' | 'elo'
export type NarrationDownloadState = 'ready' | 'preparing' | 'failed' | 'absent'
export type OutputType = 'all' | OutputKind
export type OutputSort = 'source' | 'newest' | 'difficulty' | 'type'

const UNASSIGNED = 'Unassigned'
const NO_LESSONS: Lesson[] = []
export const STUDY_MATERIAL_GROUP = 'Study Material'

export interface OutputItem {
  kind: OutputKind
  id: string
  title: string
  sourceId: string | null
  /** Class this tile opens. Null for every item filed under a book. */
  lessonId: string | null
  sourceName: string
  /** Source title. Material title for study material. */
  footer: string
  badge: string // difficulty for assessments, format for artifacts
  createdAt: string
  runnerPage: AcademyPage | null // where "Open" routes; null = artifact (reader/download)
  isAudio: boolean
  isEbook: boolean
  isNarration: boolean
  /** A finished MP3 uploaded for the source, separate from generated narration. */
  isAudiobook: boolean
  /** Narration MP3 readiness. Null for every other library item. */
  narrationDownload: NarrationDownloadState | null
  /** Knowledge run to open. Library cards leave this empty and open the whole source. */
  projectId: string | null
  /** Member text for a grouped card. Included in Library search only. */
  searchText?: string
}

// Study guides the student Library hides, plus printable study material. Questions stay visible.
export const studentHiddenLibraryKinds = ['material', 'flashcard', 'scenario'] as const satisfies readonly OutputKind[]

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
  elo: 'ELO',
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

function audiobookLength(manifest: Record<string, unknown>): string {
  const seconds = Number(manifest.duration_seconds)
  if (!Number.isFinite(seconds) || seconds <= 0) return ''
  return formatSpokenDuration(seconds)
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
  isAudiobook: boolean
} {
  const format = (artifact.format || '').toLowerCase()
  const isAudiobook = artifact.artifact_type === 'audiobook'
  const isNarration = artifact.artifact_type === 'narration_audio'
  const isAudio =
    !isNarration &&
    !isAudiobook &&
    (artifact.artifact_type.includes('audio') || AUDIO_FORMATS.has(format))
  const isEbook =
    artifact.artifact_type === 'electronic_book' || format.startsWith('epub')
  const isStudyMaterial = isStudyMaterialArtifact(artifact)

  let chipLabel = 'Artifact'
  let title = ''
  if (isStudyMaterial) {
    chipLabel = 'Material'
    title = typeof artifact.manifest.title === 'string' ? artifact.manifest.title : ''
  } else if (isAudiobook) {
    chipLabel = 'Audiobook'
    title = audiobookLength(artifact.manifest)
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

  return {
    chipLabel,
    title,
    isAudio: isAudio || isAudiobook,
    isEbook,
    isStudyMaterial,
    isNarration,
    isAudiobook,
  }
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
  if (item.isAudiobook) return 'Audiobook'
  return KIND_CHIP[item.kind]
}

const PLATOON_WORKSPACE_NAME = 'the basic school'
// Canonical title first, then the shorter labels this publication is stored under.
const PLATOON_DEFAULT_BOOKS = ['mcdp 1 warfighting', 'mcdp 1', 'warfighting'] as const

function normalizeLabel(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function normalizeBookName(name: string): string {
  return normalizeLabel(name).replace(/\.pdf$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
}

function platoonDefaultSourceId(
  books: { sourceId: string; sourceName: string }[],
): string | null {
  for (const preferred of PLATOON_DEFAULT_BOOKS) {
    const match = books.find((book) => normalizeBookName(book.sourceName) === preferred)
    if (match) return match.sourceId
  }
  return null
}

/** Reader source when the rail opens with no book in the URL. */
export function defaultReaderSourceId({
  routeSourceId,
  focusedSourceId,
  books,
  workspaceName = null,
}: {
  routeSourceId: string | null
  focusedSourceId: string | null
  books: Pick<OutputItem, 'sourceId' | 'sourceName' | 'createdAt'>[]
  workspaceName?: string | null
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
  if (normalizeLabel(workspaceName ?? '') === PLATOON_WORKSPACE_NAME) {
    const preferred = platoonDefaultSourceId(readable)
    if (preferred) return preferred
  }
  const first = [...readable].sort(
    (a, b) => a.sourceName.localeCompare(b.sourceName) || a.createdAt.localeCompare(b.createdAt),
  )[0]
  return first?.sourceId ?? null
}

const TITLE_FOOTER_KINDS = new Set<OutputKind>(['material'])

export function outputFooter(kind: OutputKind, sourceName: string, runTitle: string | null | undefined): string {
  const title = runTitle?.trim() ?? ''
  if (TITLE_FOOTER_KINDS.has(kind) && title) return title
  return sourceName
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
    if (entry.status === 'deprecated' || entry.entry_kind === 'elo') continue
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
      lessonId: null,
      sourceName,
      footer: outputFooter('wiki', sourceName, null),
      badge: '',
      createdAt: newest.created_at,
      runnerPage: 'wiki',
      isAudio: false,
      isEbook: false,
      isNarration: false,
      isAudiobook: false,
      narrationDownload: null,
      projectId: null,
      searchText: entries.map((entry) => entry.preferred_label).join(' '),
    }
  })
}

export function wikiElosToOutputItems(
  wikiEntries: WikiEntry[],
  nameOf: (id: string | null | undefined) => string,
): OutputItem[] {
  const groups = new Map<string, WikiEntry[]>()
  for (const entry of wikiEntries) {
    if (entry.status === 'deprecated' || entry.entry_kind !== 'elo') continue
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
      kind: 'elo',
      id: sourceId ?? 'unassigned',
      title: countLabel(entries.length, 'ELO'),
      sourceId,
      lessonId: null,
      sourceName,
      footer: outputFooter('elo', sourceName, null),
      badge: '',
      createdAt: newest.created_at,
      runnerPage: 'wiki',
      isAudio: false,
      isEbook: false,
      isNarration: false,
      isAudiobook: false,
      narrationDownload: null,
      projectId: null,
      searchText: entries.map((entry) => entry.preferred_label).join(' '),
    } satisfies OutputItem
  })
}

export function lessonLibraryItems(lessons: Lesson[]): OutputItem[] {
  return lessons.flatMap((lesson) => {
    const objectiveCount = lesson.objectives.length
    const resourceCount = lesson.resources.length
    if (objectiveCount === 0 && resourceCount === 0) return []
    const newestResource = lesson.resources.reduce(
      (latest, resource) => (resource.updated_at > latest ? resource.updated_at : latest),
      lesson.updated_at,
    )
    return [{
      kind: 'elo',
      id: lesson.id,
      title: objectiveCount > 0
        ? countLabel(objectiveCount, 'ELO')
        : countLabel(resourceCount, 'material'),
      sourceId: null,
      lessonId: lesson.id,
      sourceName: lesson.title,
      footer: lesson.title,
      badge: '',
      createdAt: newestResource,
      runnerPage: 'objectives',
      isAudio: false,
      isEbook: false,
      isNarration: false,
      isAudiobook: false,
      narrationDownload: null,
      projectId: null,
      searchText: [
        ...lesson.objectives.map((objective) => `${objective.text} ${objective.code ?? ''}`),
        ...lesson.resources.map((resource) => resource.label),
      ].join(' '),
    } satisfies OutputItem]
  })
}

export function outputShelfKey(item: Pick<OutputItem, 'lessonId' | 'sourceId' | 'sourceName'>): string {
  if (item.lessonId) return `lesson:${item.lessonId}`
  if (item.sourceId) return `source:${item.sourceId}`
  return `group:${item.sourceName}`
}

export type LibraryShelfSort = 'name' | 'updated'
export type BookShelfKind = 'all' | 'book' | 'audio' | 'wiki' | 'elo'
export type ClassShelfKind = 'all' | 'elo' | 'quiz'

export interface LibraryShelf {
  key: string
  name: string
  items: OutputItem[]
  updatedAt: string
}

const SHELF_KIND_RANK: Record<OutputKind, number> = {
  book: 0,
  audio: 1,
  wiki: 2,
  elo: 3,
  material: 4,
  flashcard: 5,
  question: 6,
  scenario: 7,
  artifact: 8,
}

function shelfSearchText(item: OutputItem): string {
  return `${item.title} ${item.footer} ${item.sourceName} ${outputChipLabel(item)} ${item.searchText ?? ''}`.toLowerCase()
}

function matchesShelfKind(item: OutputItem, kind: BookShelfKind | ClassShelfKind): boolean {
  if (kind === 'all') return true
  if (kind === 'quiz') return item.kind === 'question'
  return item.kind === kind
}

function shelfUpdatedAt(items: OutputItem[]): string {
  return items.reduce((latest, item) => (item.createdAt > latest ? item.createdAt : latest), '')
}

function compareShelves(sort: LibraryShelfSort, left: LibraryShelf, right: LibraryShelf): number {
  if (sort === 'name') return left.name.localeCompare(right.name)
  const leftDay = left.updatedAt.slice(0, 10)
  const rightDay = right.updatedAt.slice(0, 10)
  if (!leftDay && rightDay) return 1
  if (leftDay && !rightDay) return -1
  if (leftDay !== rightDay) return rightDay.localeCompare(leftDay)
  return left.name.localeCompare(right.name)
}

function groupShelves(items: OutputItem[], sort: LibraryShelfSort): LibraryShelf[] {
  const map = new Map<string, OutputItem[]>()
  const names = new Map<string, string>()
  for (const item of items) {
    const key = outputShelfKey(item)
    const list = map.get(key) ?? []
    list.push(item)
    map.set(key, list)
    names.set(key, item.sourceName)
  }
  return [...map.entries()]
    .map(([key, shelfItems]) => ({
      key,
      name: names.get(key) ?? '',
      items: shelfItems.toSorted((a, b) => SHELF_KIND_RANK[a.kind] - SHELF_KIND_RANK[b.kind]),
      updatedAt: shelfUpdatedAt(shelfItems),
    }))
    .sort((left, right) => compareShelves(sort, left, right))
}

/** Books above classes. A class shelf is any item with a lesson id. */
export function libraryShelves(
  items: OutputItem[],
  {
    search = '',
    bookKind = 'all',
    classKind = 'all',
    sort = 'name',
  }: {
    search?: string
    bookKind?: BookShelfKind
    classKind?: ClassShelfKind
    sort?: LibraryShelfSort
  } = {},
): { books: LibraryShelf[]; classes: LibraryShelf[] } {
  const needle = search.trim().toLowerCase()
  const visible = needle
    ? items.filter((item) => shelfSearchText(item).includes(needle))
    : items
  const books = visible.filter((item) => !item.lessonId && matchesShelfKind(item, bookKind))
  const classes = visible.filter((item) => item.lessonId && matchesShelfKind(item, classKind))
  return {
    books: groupShelves(books, sort),
    classes: groupShelves(classes, sort),
  }
}

interface KnowledgeRecord {
  id: string
  source_id?: string | null
  lesson_id?: string | null
  difficulty: string
  created_at: string
}

export function knowledgeLibraryItems<T extends KnowledgeRecord>(
  records: T[],
  {
    kind,
    runnerPage,
    unit,
    plural,
    searchOf,
    nameOf,
  }: {
    kind: 'flashcard' | 'question' | 'scenario'
    runnerPage: AcademyPage
    unit: string
    plural: string
    searchOf: (record: T) => string
    nameOf: (id: string | null | undefined) => string
  },
): OutputItem[] {
  const grouped = new Map<string, T[]>()
  for (const record of records) {
    const home = recordHome(record)
    const list = grouped.get(home.key) ?? []
    list.push(record)
    grouped.set(home.key, list)
  }

  return [...grouped.entries()].flatMap(([, batch]) => {
    const first = batch[0]
    if (!first) return []
    const home = recordHome(first)
    const sourceName = nameOf(home.lessonId ?? home.sourceId)
    const newest = batch.reduce((latest, record) =>
      record.created_at > latest.created_at ? record : latest,
    )
    return [{
      kind,
      id: home.lessonId ?? home.sourceId ?? 'unassigned',
      projectId: null,
      title: countLabel(batch.length, unit, plural),
      sourceId: home.sourceId,
      lessonId: home.lessonId,
      sourceName,
      footer: sourceName,
      badge: '',
      createdAt: newest.created_at,
      runnerPage,
      isAudio: false,
      isEbook: false,
      isNarration: false,
      isAudiobook: false,
      narrationDownload: null,
      searchText: batch.map(searchOf).join(' '),
    } satisfies OutputItem]
  })
}

function recordHome(record: KnowledgeRecord): { key: string; sourceId: string | null; lessonId: string | null } {
  const lessonId = record.lesson_id ?? null
  if (lessonId) return { key: `lesson:${lessonId}`, sourceId: null, lessonId }
  const sourceId = record.source_id ?? null
  return { key: sourceId ?? '', sourceId, lessonId: null }
}

export function useOutputs(): { items: OutputItem[]; sources: { id: string; name: string }[] } {
  const { quizzes, scenarios, artifacts, wikiEntries, sources } = useWorkspaceData()
  const { activeWorkspace } = useWorkspace()
  const { lessons, isLoading: lessonsLoading } = useLessons(activeWorkspace?.id ?? null)
  const readyLessons = lessonsLoading ? NO_LESSONS : lessons

  return useMemo(() => {
    const byId = new Map(sources.map((s) => [s.id, s]))
    const lessonTitles = new Map(readyLessons.map((lesson) => [lesson.id, lesson.title]))
    const nameOf = (id: string | null | undefined) => {
      if (!id) return UNASSIGNED
      return lessonTitles.get(id) ?? sourceLabel(byId.get(id))
    }

    // Flashcards and wiki-term questions live only on the Flashcards tab.
    const libraryQuizzes = quizzes.filter((quiz) => !isWikiTermQuiz(quiz))

    const items: OutputItem[] = [
      ...knowledgeLibraryItems(libraryQuizzes, {
        kind: 'question',
        runnerPage: 'quiz',
        unit: 'question',
        plural: 'questions',
        searchOf: (quiz) => quiz.question,
        nameOf,
      }),
      ...knowledgeLibraryItems(scenarios, {
        kind: 'scenario',
        runnerPage: 'scenarios',
        unit: 'scenario',
        plural: 'scenarios',
        searchOf: (scenario) => `${scenario.title} ${scenario.prompt}`,
        nameOf,
      }),
      ...wikiEntriesToOutputItems(wikiEntries, nameOf),
      ...wikiElosToOutputItems(wikiEntries, nameOf),
      ...lessonLibraryItems(readyLessons),
      ...collapseDuplicateNarrationArtifacts(artifacts)
        .filter((a) => !isIncompleteNarrationArtifact(a))
        .map<OutputItem>((a) => {
        const card = artifactLibraryCard(a)
        const kind: OutputItem['kind'] = card.isStudyMaterial
          ? 'material'
          : card.isEbook
            ? 'book'
            : card.isAudio || card.isNarration || card.isAudiobook
              ? 'audio'
              : 'artifact'
        const sourceName = card.isStudyMaterial ? STUDY_MATERIAL_GROUP : nameOf(a.source_id)
        const materialTitle = typeof a.manifest.title === 'string' ? a.manifest.title : ''
        return {
          kind,
          id: a.id,
          title: card.title,
          sourceId: a.source_id ?? null,
          lessonId: null,
          sourceName,
          footer: outputFooter(kind, sourceName, card.isStudyMaterial ? materialTitle : null),
          badge: (a.format || 'file').toUpperCase(),
          createdAt: a.created_at,
          runnerPage: null,
          isAudio: card.isAudio,
          isEbook: card.isEbook,
          isNarration: card.isNarration,
          isAudiobook: card.isAudiobook,
          narrationDownload: card.isNarration ? narrationDownloadState(a.manifest) : null,
          projectId: null,
        }
      }),
    ]

    // Distinct sources that actually have outputs, sorted by name.
    const seen = new Map<string, string>()
    for (const item of items) {
      const id = item.lessonId ?? item.sourceId
      if (id && !seen.has(id)) seen.set(id, item.sourceName)
    }
    const sourceList = [...seen.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name))

    return { items, sources: sourceList }
  }, [quizzes, scenarios, artifacts, wikiEntries, sources, readyLessons])
}

export function filterOutputs(
  items: OutputItem[],
  { search, type, sourceId }: { search: string; type: OutputType; sourceId: string | null },
): OutputItem[] {
  const q = search.trim().toLowerCase()
  return items.filter((item) => {
    if (type !== 'all' && item.kind !== type) return false
    if (sourceId && item.sourceId !== sourceId && item.lessonId !== sourceId) return false
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
