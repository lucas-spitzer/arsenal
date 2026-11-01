import {
  BookMarked,
  BookOpen,
  ChevronRight,
  Download,
  FileText,
  Headphones,
  HelpCircle,
  Layers,
  Lightbulb,
  Star,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { isFocused, useLibraryFocus, type LibraryFocusState } from '../../lib/libraryFocus'
import {
  filterOutputs,
  libraryItemsForRole,
  isStudentHiddenLibraryKind,
  outputChipLabel,
  sortOutputs,
  studentHiddenLibraryKinds,
  useOutputs,
  type OutputItem,
  type OutputSort,
  type OutputType,
} from '../../lib/academyOutputs'
import { getArtifactDownloadUrl } from '../../lib/workspaceApi'
import { FoundryLoader } from '../foundry/FoundryLoader'
import { OutputFilterBar } from './OutputFilterBar'
import { StudyHead } from './StudySessionChrome'
import type { AcademyPage, AcademyScope } from './types'

const KIND_META: Record<
  OutputItem['kind'],
  { cls: string; icon: typeof Layers }
> = {
  audio: { cls: 'lib__tchip--audio', icon: Headphones },
  book: { cls: 'lib__tchip--book', icon: BookOpen },
  artifact: { cls: 'lib__tchip--art', icon: Headphones },
  material: { cls: 'lib__tchip--mat', icon: FileText },
  flashcard: { cls: 'lib__tchip--flash', icon: Layers },
  question: { cls: 'lib__tchip--q', icon: HelpCircle },
  scenario: { cls: 'lib__tchip--scn', icon: Lightbulb },
  wiki: { cls: 'lib__tchip--wiki', icon: BookMarked },
}

const KIND_RANK: Record<OutputItem['kind'], number> = {
  book: 0,
  audio: 1,
  wiki: 2,
  material: 3,
  flashcard: 4,
  question: 5,
  scenario: 6,
  artifact: 7,
}

// Study material and plain audio files already download from the open action.
function canDownload(item: OutputItem): boolean {
  if (item.kind === 'book') return true
  return item.kind === 'audio' && (item.isNarration || item.isAudiobook)
}

function downloadTitle(item: OutputItem): string {
  if (item.narrationDownload === 'preparing') return 'Preparing the audio file'
  if (item.narrationDownload === 'failed') return 'Could not prepare the audio file. Try again.'
  if (item.kind === 'book') return 'Download book'
  if (item.kind === 'material') return 'Download study material'
  if (item.isAudiobook) return 'Download audiobook'
  return 'Download audio'
}

function openLabel(item: OutputItem): string {
  if (item.isAudiobook) return 'Play'
  switch (item.kind) {
    case 'book':
    case 'artifact':
      return 'Read'
    case 'audio':
      return item.isNarration ? 'Listen' : 'Download'
    case 'material':
      return 'Download'
    case 'flashcard':
      return 'Study'
    case 'wiki':
    case 'question':
    case 'scenario':
      return 'Open'
    default: {
      const _exhaustive: never = item.kind
      return _exhaustive
    }
  }
}

type TileMode = 'shelf' | 'flat'

function joinParts(parts: string[]): string {
  return [...new Set(parts.filter(Boolean))].join(' · ')
}

// Shelf tiles sit under a source header, so they lead with the kind.
// Flat tiles lead with the source (or run/material title) instead.
function tileText(
  item: OutputItem,
  { mode, showKind }: { mode: TileMode; showKind: boolean },
): { main: string; sub: string } {
  const chip = outputChipLabel(item)
  if (mode === 'shelf') {
    const runTitle = item.footer === item.sourceName ? '' : item.footer
    return { main: chip, sub: joinParts([item.title, runTitle]) }
  }
  return {
    main: item.footer,
    sub: joinParts([showKind ? chip : '', item.title === item.footer ? '' : item.title]),
  }
}

function outputCount(n: number): string {
  return `${n} ${n === 1 ? 'output' : 'outputs'}`
}

function shelfMeta(items: OutputItem[]): string {
  const newest = items.reduce((latest, item) => (item.createdAt > latest ? item.createdAt : latest), '')
  if (!newest) return outputCount(items.length)
  const updated = new Date(newest).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${outputCount(items.length)} · Updated ${updated}`
}

export function LibraryView({
  onOpen,
}: {
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}) {
  const { items: catalogItems, sources: catalogSources } = useOutputs()
  const { approvedUser } = useAuth()
  const isAdmin = isAdminAccess(approvedUser?.role)
  const items = useMemo(
    () => libraryItemsForRole(catalogItems, isAdmin),
    [catalogItems, isAdmin],
  )
  const sources = useMemo(() => {
    const ids = new Set(items.flatMap((item) => (item.sourceId ? [item.sourceId] : [])))
    return catalogSources.filter((source) => ids.has(source.id))
  }, [catalogSources, items])
  const { downloadArtifact, error, isLoading } = useWorkspaceData()
  const { activeWorkspace } = useWorkspace()
  const { focus, toggleFocus } = useLibraryFocus(activeWorkspace?.id ?? null)
  const navigate = useNavigate()

  const [player, setPlayer] = useState<{ title: string; url: string } | null>(null)
  const [playError, setPlayError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [type, setType] = useState<OutputType>('all')
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [sort, setSort] = useState<OutputSort>('source')
  const visibleType =
    !isAdmin && type !== 'all' && isStudentHiddenLibraryKind(type) ? 'all' : type
  const visibleSourceId = sourceId && sources.some((source) => source.id === sourceId) ? sourceId : null

  const filtered = useMemo(() => {
    const sorted = sortOutputs(
      filterOutputs(items, { search, type: visibleType, sourceId: visibleSourceId }),
      sort,
    )
    // Focused items float to the front, keeping their relative sort order.
    return [
      ...sorted.filter((item) => isFocused(focus, item)),
      ...sorted.filter((item) => !isFocused(focus, item)),
    ]
  }, [items, search, visibleType, visibleSourceId, sort, focus])

  const groups = useMemo(() => {
    if (sort !== 'source' || visibleType !== 'all') return null
    const map = new Map<string, OutputItem[]>()
    for (const item of filtered) {
      const list = map.get(item.sourceName) ?? []
      list.push(item)
      map.set(item.sourceName, list)
    }
    return [...map.entries()].map(([sourceName, list]): [string, OutputItem[]] => [
      sourceName,
      list.toSorted((a, b) => KIND_RANK[a.kind] - KIND_RANK[b.kind]),
    ])
  }, [filtered, sort, visibleType])

  const playAudiobook = async (item: OutputItem) => {
    setPlayError(null)
    try {
      const result = await getArtifactDownloadUrl(item.id)
      if (!result.download_url) {
        setPlayError('That audiobook is not ready to play.')
        return
      }
      setPlayer({ title: item.title || item.sourceName, url: result.download_url })
    } catch (caught) {
      setPlayError(caught instanceof Error ? caught.message : 'Could not play that audiobook.')
    }
  }

  const handleOpen = (item: OutputItem) => {
    if (item.isAudiobook) {
      void playAudiobook(item)
      return
    }
    if (item.kind === 'material') {
      void downloadArtifact(item.id)
      return
    }
    if (item.kind === 'audio') {
      if (item.isNarration) {
        if (item.sourceId) navigate(`/app/reader/${item.sourceId}`)
      } else {
        void downloadArtifact(item.id)
      }
      return
    }
    if (item.kind === 'book' || item.kind === 'artifact') {
      if (item.sourceId) navigate(`/app/reader/${item.sourceId}`)
      return
    }
    if (item.kind === 'wiki') {
      onOpen('wiki', { sourceId: item.sourceId, targetId: null, projectId: null })
      return
    }
    if (item.kind === 'flashcard' || item.kind === 'question' || item.kind === 'scenario') {
      if (item.runnerPage) {
        onOpen(item.runnerPage, {
          sourceId: item.sourceId,
          targetId: null,
          projectId: null,
        })
      }
      return
    }
    if (item.runnerPage) {
      onOpen(item.runnerPage, {
        sourceId: item.sourceId,
        targetId: item.projectId ? null : item.id,
        projectId: item.projectId,
      })
    }
  }

  const tileActions: TileActions = {
    focus,
    onOpen: handleOpen,
    onDownload: (item) => void downloadArtifact(item.id),
    onToggleFocus: toggleFocus,
  }

  return (
    <section className="lib study-session" aria-busy={isLoading}>
      <StudyHead
        eyebrow="Workspace catalog"
        title="Library"
        description={
          isAdmin
            ? 'Search, filter, and open every book, audio file, study material, wiki entry, flashcard, question, and scenario in this workspace.'
            : 'Search, filter, and open the books, audio, and wiki entries in this workspace.'
        }
        stats={[
          { value: filtered.length, label: 'outputs' },
          { value: sources.length, label: 'sources' },
        ]}
      />

      <OutputFilterBar
        search={search}
        onSearch={setSearch}
        type={visibleType}
        onType={setType}
        sourceId={visibleSourceId}
        onSource={setSourceId}
        sort={sort}
        onSort={setSort}
        sources={sources}
        hiddenTypes={isAdmin ? undefined : studentHiddenLibraryKinds}
        searchPlaceholder={
          isAdmin
            ? 'Search flashcards, questions, scenarios, wiki, books, audio, study material…'
            : 'Search books, audio, and wiki entries…'
        }
      />

      {playError ? <p className="lib__play-error">{playError}</p> : null}

      {isLoading && items.length === 0 ? (
        <div className="lib__empty">
          <FoundryLoader label="Loading library" size="sm" />
        </div>
      ) : error && items.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">Library unavailable</p>
          <p className="lib__empty-copy">{error}</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">No matching outputs</p>
          <p className="lib__empty-copy">
            Adjust the filters, or generate material for a source in the console.
          </p>
        </div>
      ) : groups ? (
        <SourceShelves groups={groups} {...tileActions} />
      ) : (
        <TileGrid items={filtered} showKind={visibleType === 'all'} {...tileActions} />
      )}
      {player ? (
        <div className="lib__player">
          <p className="lib__player-title">{player.title}</p>
          <audio key={player.url} controls autoPlay src={player.url} />
        </div>
      ) : null}
    </section>
  )
}

type TileActions = {
  focus: LibraryFocusState
  onOpen: (item: OutputItem) => void
  onDownload: (item: OutputItem) => void
  onToggleFocus: (item: OutputItem) => void
}

function SourceShelves({
  groups,
  ...actions
}: TileActions & { groups: [string, OutputItem[]][] }) {
  return (
    <div className="lib__shelves">
      {groups.map(([sourceName, list]) => (
        <section key={sourceName} className="lib__shelf">
          <div className="lib__shelf-head">
            <h3 className="lib__shelf-title">{sourceName}</h3>
            <span className="lib__shelf-meta">{shelfMeta(list)}</span>
          </div>
          <div className="lib__shelf-items">
            {list.map((item) => (
              <OutputTile
                key={`${item.kind}-${item.id}`}
                item={item}
                mode="shelf"
                showKind
                {...actions}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function TileGrid({
  items,
  showKind,
  ...actions
}: TileActions & { items: OutputItem[]; showKind: boolean }) {
  return (
    <div className="lib__tiles">
      {items.map((item) => (
        <OutputTile
          key={`${item.kind}-${item.id}`}
          item={item}
          mode="flat"
          showKind={showKind}
          {...actions}
        />
      ))}
    </div>
  )
}

function OutputTile({
  item,
  mode,
  showKind,
  focus,
  onOpen,
  onDownload,
  onToggleFocus,
}: TileActions & { item: OutputItem; mode: TileMode; showKind: boolean }) {
  const meta = KIND_META[item.kind]
  const Icon = meta.icon
  const focused = isFocused(focus, item)
  const { main, sub } = tileText(item, { mode, showKind })
  const verb = openLabel(item)
  return (
    <article className="lib__tile">
      <span className={`lib__tile-icon ${meta.cls}`}>
        <Icon size={16} aria-hidden="true" />
      </span>
      <div className="lib__tile-text">
        <p className="lib__tile-main" title={main}>
          {main}
        </p>
        {sub ? (
          <p className="lib__tile-sub" title={sub}>
            {sub}
          </p>
        ) : null}
      </div>
      <div className="lib__tile-actions">
        {canDownload(item) ? (
          <button
            type="button"
            className="lib__focus"
            onClick={() => onDownload(item)}
            disabled={item.narrationDownload === 'preparing'}
            title={downloadTitle(item)}
            aria-label={downloadTitle(item)}
          >
            <Download size={14} aria-hidden="true" />
          </button>
        ) : null}
        <button
          type="button"
          className={`lib__focus${focused ? ' is-focused' : ''}`}
          onClick={() => onToggleFocus(item)}
          title={
            focused
              ? 'Remove focus'
              : item.isEbook
                ? 'Focus this ebook (becomes the default in the reader)'
                : 'Focus this item'
          }
          aria-pressed={focused}
          aria-label={focused ? 'Remove focus' : 'Focus this item'}
        >
          <Star size={14} aria-hidden="true" />
        </button>
      </div>
      <button
        type="button"
        className="lib__open lib__tile-open"
        onClick={() => onOpen(item)}
        aria-label={`${verb} ${outputChipLabel(item)}, ${item.footer}`}
      >
        {verb}
        <ChevronRight size={12} aria-hidden="true" />
      </button>
    </article>
  )
}
