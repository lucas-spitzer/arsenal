import { ArrowDownUp, BookMarked, Headphones, HelpCircle, Layers, LayoutGrid, Lightbulb, Search } from 'lucide-react'
import type { OutputSort, OutputType } from '../../lib/academyOutputs'

const TYPE_CHIPS: { value: OutputType; label: string; icon: typeof LayoutGrid }[] = [
  { value: 'all', label: 'All', icon: LayoutGrid },
  { value: 'artifact', label: 'Artifacts', icon: Headphones },
  { value: 'wiki', label: 'Wiki', icon: BookMarked },
  { value: 'flashcard', label: 'Flashcards', icon: Layers },
  { value: 'question', label: 'Questions', icon: HelpCircle },
  { value: 'scenario', label: 'Scenarios', icon: Lightbulb },
]

const SORT_OPTIONS: { value: OutputSort; label: string }[] = [
  { value: 'source', label: 'Source' },
  { value: 'newest', label: 'Newest' },
  { value: 'difficulty', label: 'Difficulty' },
  { value: 'type', label: 'Type' },
]

type Props = {
  search?: string
  onSearch?: (value: string) => void
  type?: OutputType
  onType?: (value: OutputType) => void
  sourceId: string | null
  onSource: (value: string | null) => void
  sort: OutputSort
  onSort: (value: OutputSort) => void
  sources: { id: string; name: string }[]
  showTypes?: boolean
  showSearch?: boolean
  searchPlaceholder?: string
}

export function OutputFilterBar({
  search = '',
  onSearch,
  type = 'all',
  onType,
  sourceId,
  onSource,
  sort,
  onSort,
  sources,
  showTypes = true,
  showSearch = true,
  searchPlaceholder = 'Search…',
}: Props) {
  return (
    <div className="lib__filter">
      <div className="lib__bar">
        {showSearch && onSearch && (
          <div className="lib__search">
            <Search size={16} aria-hidden="true" />
            <input
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              placeholder={searchPlaceholder}
              aria-label="Search outputs"
            />
          </div>
        )}

        <label className="lib__select">
          <span className="lib__select-label">Source</span>
          <select
            value={sourceId ?? ''}
            onChange={(e) => onSource(e.target.value || null)}
            aria-label="Filter by source"
          >
            <option value="">All</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label className="lib__select">
          <span className="lib__select-label">Sort</span>
          <ArrowDownUp size={14} aria-hidden="true" />
          <select
            value={sort}
            onChange={(e) => onSort(e.target.value as OutputSort)}
            aria-label="Sort outputs"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {showTypes && onType && (
        <div className="lib__chips" role="group" aria-label="Filter by type">
          {TYPE_CHIPS.map((chip) => {
            const Icon = chip.icon
            return (
              <button
                key={chip.value}
                type="button"
                className={`lib__chip${type === chip.value ? ' is-active' : ''}`}
                onClick={() => onType(chip.value)}
                aria-pressed={type === chip.value}
              >
                <Icon size={14} aria-hidden="true" />
                {chip.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
