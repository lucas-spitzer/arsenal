import { BookMarked, BookOpen, FileText, Headphones, HelpCircle, Layers, Lightbulb, Star } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { isFocused, useLibraryFocus, type LibraryFocusState } from '../../lib/libraryFocus'
import {
  filterOutputs,
  outputChipLabel,
  sortOutputs,
  useOutputs,
  type OutputItem,
  type OutputSort,
  type OutputType,
} from '../../lib/academyOutputs'
import { OutputFilterBar } from './OutputFilterBar'
import { StudyHead } from './StudySessionChrome'
import type { AcademyPage, AcademyScope } from './types'

const KIND_META: Record<
  OutputItem['kind'],
  { cls: string; icon: typeof Layers }
> = {
  artifact: { cls: 'lib__tchip--art', icon: Headphones },
  material: { cls: 'lib__tchip--mat', icon: FileText },
  flashcard: { cls: 'lib__tchip--flash', icon: Layers },
  question: { cls: 'lib__tchip--q', icon: HelpCircle },
  scenario: { cls: 'lib__tchip--scn', icon: Lightbulb },
  wiki: { cls: 'lib__tchip--wiki', icon: BookMarked },
}

function cardIcon(item: OutputItem): typeof Layers {
  if (item.kind !== 'artifact') return KIND_META[item.kind].icon
  if (item.isEbook) return BookOpen
  return Headphones
}

function openLabel(item: OutputItem): string {
  if (item.kind === 'material') return 'Download'
  if (item.kind === 'artifact') {
    if (item.isAudio) return 'Download'
    return 'Open'
  }
  if (item.kind === 'flashcard') return 'Study'
  if (item.kind === 'wiki') return 'Edit'
  return 'Open'
}

export function LibraryView({
  onOpen,
}: {
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}) {
  const { items, sources } = useOutputs()
  const { downloadArtifact } = useWorkspaceData()
  const { activeWorkspace } = useWorkspace()
  const { focus, toggleFocus } = useLibraryFocus(activeWorkspace?.id ?? null)
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [type, setType] = useState<OutputType>('all')
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [sort, setSort] = useState<OutputSort>('source')

  const filtered = useMemo(() => {
    const sorted = sortOutputs(filterOutputs(items, { search, type, sourceId }), sort)
    // Focused items float to the front, keeping their relative sort order.
    return [
      ...sorted.filter((item) => isFocused(focus, item)),
      ...sorted.filter((item) => !isFocused(focus, item)),
    ]
  }, [items, search, type, sourceId, sort, focus])

  const groups = useMemo(() => {
    if (sort !== 'source') return null
    const map = new Map<string, OutputItem[]>()
    for (const item of filtered) {
      const list = map.get(item.sourceName) ?? []
      list.push(item)
      map.set(item.sourceName, list)
    }
    return [...map.entries()]
  }, [filtered, sort])

  const handleOpen = (item: OutputItem) => {
    if (item.kind === 'material') {
      void downloadArtifact(item.id)
      return
    }
    if (item.kind === 'artifact') {
      if (item.isAudio) void downloadArtifact(item.id)
      else if (item.sourceId) navigate(`/app/reader/${item.sourceId}`)
      return
    }
    if (item.runnerPage) onOpen(item.runnerPage, { sourceId: item.sourceId, targetId: item.id })
  }

  return (
    <section className="lib study-session">
      <StudyHead
        eyebrow="Workspace catalog"
        title="Library"
        description="Search, filter, and open every artifact, study material, wiki entry, flashcard, question, and scenario in this workspace."
        stats={[
          { value: filtered.length, label: 'outputs' },
          { value: sources.length, label: 'sources' },
        ]}
      />

      <OutputFilterBar
        search={search}
        onSearch={setSearch}
        type={type}
        onType={setType}
        sourceId={sourceId}
        onSource={setSourceId}
        sort={sort}
        onSort={setSort}
        sources={sources}
        searchPlaceholder="Search flashcards, questions, scenarios, wiki, artifacts, study material…"
      />

      {filtered.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">No matching outputs</p>
          <p className="lib__empty-copy">
            Adjust the filters, or generate material for a source in the console.
          </p>
        </div>
      ) : groups ? (
        groups.map(([sourceName, list]) => (
          <div key={sourceName}>
            <div className="lib__band">
              <h3 className="lib__band-title">{sourceName}</h3>
              <span className="lib__band-line" />
              <span className="lib__band-count">{list.length} outputs</span>
            </div>
            <CardGrid items={list} onOpen={handleOpen} focus={focus} onToggleFocus={toggleFocus} />
          </div>
        ))
      ) : (
        <CardGrid items={filtered} onOpen={handleOpen} focus={focus} onToggleFocus={toggleFocus} />
      )}
    </section>
  )
}

function CardGrid({
  items,
  onOpen,
  focus,
  onToggleFocus,
}: {
  items: OutputItem[]
  onOpen: (item: OutputItem) => void
  focus: LibraryFocusState
  onToggleFocus: (item: OutputItem) => void
}) {
  return (
    <div className="lib__grid">
      {items.map((item) => {
        const meta = KIND_META[item.kind]
        const Icon = cardIcon(item)
        const focused = isFocused(focus, item)
        const chip = outputChipLabel(item)
        const spec = item.kind === 'artifact' || item.kind === 'material'
        return (
          <article key={`${item.kind}-${item.id}`} className="lib__card">
            <div className="lib__card-top">
              <span className={`lib__tchip ${meta.cls}`}>
                <Icon size={12} aria-hidden="true" />
                {chip}
              </span>
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
            {item.title ? (
              <p className={spec ? 'lib__pv lib__pv--fact' : 'lib__pv'}>{item.title}</p>
            ) : null}
            <div className="lib__fill" />
            <div className="lib__foot">
              <div className="lib__meta">
                <span>{item.sourceName}</span>
              </div>
              <button type="button" className="lib__open" onClick={() => onOpen(item)}>
                {openLabel(item)}
              </button>
            </div>
          </article>
        )
      })}
    </div>
  )
}
