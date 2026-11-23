import {
  BookMarked,
  BookOpen,
  ChevronRight,
  Download,
  FileText,
  Headphones,
  HelpCircle,
  Layers,
  LayoutGrid,
  Lightbulb,
  Star,
  Target,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { isFocused, useLibraryFocus, type LibraryFocusState } from '../../lib/libraryFocus'
import {
  libraryItemsForRole,
  libraryShelves,
  outputChipLabel,
  useOutputs,
  type BookShelfKind,
  type ClassShelfKind,
  type LibraryShelf,
  type LibraryShelfSort,
  type OutputItem,
} from '../../lib/academyOutputs'
import { getArtifactDownloadUrl } from '../../lib/workspaceApi'
import { Loader } from '../shared/Loader'
import { useAcademyChrome } from './academyChromeContext'
import { LibraryKindChips, OutputFilterBar } from './OutputFilterBar'

const BOOK_KIND_CHIPS = [
  { value: 'all' as const, label: 'All', icon: LayoutGrid },
  { value: 'book' as const, label: 'Book', icon: BookOpen },
  { value: 'audio' as const, label: 'Audio', icon: Headphones },
  { value: 'wiki' as const, label: 'Wiki', icon: BookMarked },
  { value: 'elo' as const, label: 'ELO', icon: Target },
]

const CLASS_KIND_CHIPS = [
  { value: 'all' as const, label: 'All', icon: LayoutGrid },
  { value: 'elo' as const, label: 'ELO', icon: Target },
  { value: 'quiz' as const, label: 'Quiz', icon: HelpCircle },
]
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
  elo: { cls: 'lib__tchip--elo', icon: Target },
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
    case 'elo':
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
  const { items: catalogItems } = useOutputs()
  const { approvedUser } = useAuth()
  const isAdmin = isAdminAccess(approvedUser?.role)
  const items = useMemo(
    () => libraryItemsForRole(catalogItems, isAdmin),
    [catalogItems, isAdmin],
  )
  const { downloadArtifact, error, isLoading } = useWorkspaceData()
  const { activeWorkspace } = useWorkspace()
  const { focus, toggleFocus } = useLibraryFocus(activeWorkspace?.id ?? null)
  const { compact } = useAcademyChrome()
  const navigate = useNavigate()

  const [player, setPlayer] = useState<{ title: string; url: string } | null>(null)
  const [playError, setPlayError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [bookKind, setBookKind] = useState<BookShelfKind>('all')
  const [classKind, setClassKind] = useState<ClassShelfKind>('all')
  const [sort, setSort] = useState<LibraryShelfSort>('name')

  const catalog = useMemo(
    () => libraryShelves(items, { search, sort }),
    [items, search, sort],
  )
  const sections = useMemo(() => {
    const next = libraryShelves(items, { search, bookKind, classKind, sort })
    return {
      books: floatFocusedShelves(next.books, focus),
      classes: floatFocusedShelves(next.classes, focus),
    }
  }, [items, search, bookKind, classKind, sort, focus])
  const visibleCount =
    sections.books.reduce((total, shelf) => total + shelf.items.length, 0) +
    sections.classes.reduce((total, shelf) => total + shelf.items.length, 0)
  const shelfCount = sections.books.length + sections.classes.length

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
    if (item.kind === 'elo') {
      if (item.lessonId) {
        navigate(`/app/elo/${item.lessonId}`)
        return
      }
      onOpen('wiki', {
        sourceId: item.sourceId,
        targetId: null,
        projectId: null,
        wikiKind: 'elo',
      })
      return
    }
    if (item.kind === 'wiki') {
      onOpen('wiki', { sourceId: item.sourceId, targetId: null, projectId: null, wikiKind: null })
      return
    }
    if (item.kind === 'flashcard' || item.kind === 'question' || item.kind === 'scenario') {
      if (item.runnerPage) {
        onOpen(item.runnerPage, {
          sourceId: item.lessonId ?? item.sourceId,
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
            ? 'Search, filter, and open every book, audio file, study material, wiki entry, ELO, question, and scenario in this workspace.'
            : 'Search, filter, and open the books, audio, wiki entries, and ELOs in this workspace.'
        }
        stats={[
          { value: visibleCount, label: 'outputs' },
          { value: shelfCount, label: 'shelves' },
        ]}
      />

      <OutputFilterBar
        search={search}
        onSearch={setSearch}
        sort={sort}
        onSort={setSort}
        bookKind={bookKind}
        classKind={classKind}
        filters={
          <>
            <div className="lib__sheet-kinds">
              <p className="lib__sheet-kinds-label">Books</p>
              <LibraryKindChips
                label="Book items"
                value={bookKind}
                onChange={setBookKind}
                chips={BOOK_KIND_CHIPS}
              />
            </div>
            <div className="lib__sheet-kinds">
              <p className="lib__sheet-kinds-label">Classes</p>
              <LibraryKindChips
                label="Class items"
                value={classKind}
                onChange={setClassKind}
                chips={CLASS_KIND_CHIPS}
              />
            </div>
          </>
        }
        searchPlaceholder={
          isAdmin
            ? 'Search questions, scenarios, wiki, books, audio, study material…'
            : 'Search books, audio, wiki entries, and ELOs…'
        }
      />

      {playError ? <p className="lib__play-error">{playError}</p> : null}

      {isLoading && items.length === 0 ? (
        <div className="lib__empty">
          <Loader label="Loading library" size="sm" />
        </div>
      ) : error && items.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">Library unavailable</p>
          <p className="lib__empty-copy">{error}</p>
        </div>
      ) : catalog.books.length === 0 && catalog.classes.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">No matching outputs</p>
          <p className="lib__empty-copy">
            Adjust the filters, or generate material for a source in the console.
          </p>
        </div>
      ) : (
        <div className="lib__sections">
          <ShelfSection
            title="Books"
            shelves={sections.books}
            showEmpty={catalog.books.length > 0 && sections.books.length === 0}
            emptyCopy="No matching books."
            chips={
              compact ? null : (
                <LibraryKindChips
                  label="Book items"
                  value={bookKind}
                  onChange={setBookKind}
                  chips={BOOK_KIND_CHIPS}
                />
              )
            }
            {...tileActions}
          />
          <ShelfSection
            title="Classes"
            shelves={sections.classes}
            showEmpty={catalog.classes.length > 0 && sections.classes.length === 0}
            emptyCopy="No matching classes."
            chips={
              compact ? null : (
                <LibraryKindChips
                  label="Class items"
                  value={classKind}
                  onChange={setClassKind}
                  chips={CLASS_KIND_CHIPS}
                />
              )
            }
            {...tileActions}
          />
        </div>
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

function floatFocusedShelves(shelves: LibraryShelf[], focus: LibraryFocusState): LibraryShelf[] {
  return [
    ...shelves.filter((shelf) => shelf.items.some((item) => isFocused(focus, item))),
    ...shelves.filter((shelf) => !shelf.items.some((item) => isFocused(focus, item))),
  ]
}

function ShelfSection({
  title,
  shelves,
  showEmpty,
  emptyCopy,
  chips,
  ...actions
}: TileActions & {
  title: string
  shelves: LibraryShelf[]
  showEmpty: boolean
  emptyCopy: string
  chips: ReactNode
}) {
  if (shelves.length === 0 && !showEmpty) return null
  return (
    <section className="lib__section" aria-label={title}>
      <div className="lib__band">
        <h3 className="lib__band-title">{title}</h3>
        <span className="lib__band-line" />
      </div>
      {chips}
      {shelves.length > 0 ? <SourceShelves groups={shelves} {...actions} /> : null}
      {showEmpty ? <p className="lib__section-empty">{emptyCopy}</p> : null}
    </section>
  )
}

function SourceShelves({
  groups,
  ...actions
}: TileActions & { groups: LibraryShelf[] }) {
  return (
    <div className="lib__shelves">
      {groups.map((group) => (
        <section key={group.key} className="lib__shelf">
          <div className="lib__shelf-head">
            <h3 className="lib__shelf-title">{group.name}</h3>
            <span className="lib__shelf-meta">{shelfMeta(group.items)}</span>
          </div>
          <div className="lib__shelf-items">
            {group.items.map((item) => (
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
