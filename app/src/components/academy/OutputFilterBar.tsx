import { ArrowDownUp, Search, SlidersHorizontal, X, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { BookShelfKind, ClassShelfKind, LibraryShelfSort } from '../../lib/academyOutputs'
import { useAcademyChrome } from './academyChromeContext'

type KindChip<T extends string> = { value: T; label: string; icon: LucideIcon }

const SORT_OPTIONS: { value: LibraryShelfSort; label: string }[] = [
  { value: 'name', label: 'Name' },
  { value: 'updated', label: 'Updated' },
]

export function LibraryKindChips<T extends string>({
  label,
  value,
  onChange,
  chips,
}: {
  label: string
  value: T
  onChange: (value: T) => void
  chips: KindChip<T>[]
}) {
  return (
    <div className="lib__chips" role="group" aria-label={label}>
      {chips.map((chip) => {
        const Icon = chip.icon
        return (
          <button
            key={chip.value}
            type="button"
            className={`lib__chip${value === chip.value ? ' is-active' : ''}`}
            onClick={() => onChange(chip.value)}
            aria-pressed={value === chip.value}
          >
            <Icon size={14} aria-hidden="true" />
            {chip.label}
          </button>
        )
      })}
    </div>
  )
}

export function OutputFilterBar({
  search = '',
  onSearch,
  sort,
  onSort,
  bookKind,
  classKind,
  showSearch = true,
  searchPlaceholder = 'Search…',
  filters = null,
}: {
  search?: string
  onSearch?: (value: string) => void
  sort: LibraryShelfSort
  onSort: (value: LibraryShelfSort) => void
  bookKind: BookShelfKind
  classKind: ClassShelfKind
  showSearch?: boolean
  searchPlaceholder?: string
  filters?: ReactNode
}) {
  const { compact } = useAcademyChrome()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const activeFilters =
    (bookKind !== 'all' ? 1 : 0) + (classKind !== 'all' ? 1 : 0) + (sort !== 'name' ? 1 : 0)

  const sortSelect = (
    <label className="lib__select">
      <span className="lib__select-label">Sort</span>
      <ArrowDownUp size={14} aria-hidden="true" />
      <select
        value={sort}
        onChange={(event) => {
          const next = event.target.value
          if (next === 'name' || next === 'updated') onSort(next)
        }}
        aria-label="Sort shelves"
      >
        {SORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )

  const searchField = showSearch && onSearch ? (
    <div className="lib__search">
      <Search size={16} aria-hidden="true" />
      <input
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        placeholder={searchPlaceholder}
        aria-label="Search outputs"
      />
    </div>
  ) : null

  if (compact) {
    return (
      <div className="lib__filter lib__filter--compact">
        <div className="lib__bar">
          {searchField}
          <button
            type="button"
            className={`lib__filter-toggle${activeFilters > 0 ? ' is-active' : ''}`}
            onClick={() => setFiltersOpen(true)}
            aria-expanded={filtersOpen}
            aria-label="Open filters"
          >
            <SlidersHorizontal size={16} aria-hidden />
            Filters
            {activeFilters > 0 ? <span className="lib__filter-count">{activeFilters}</span> : null}
          </button>
        </div>

        {filtersOpen && (
          <div
            className="lib__filter-sheet-backdrop"
            onClick={() => setFiltersOpen(false)}
            role="presentation"
          >
            <div
              className="lib__filter-sheet"
              role="dialog"
              aria-modal="true"
              aria-label="Library filters"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="lib__filter-sheet-head">
                <p className="lib__filter-sheet-title">Filters</p>
                <button
                  type="button"
                  className="lib__filter-sheet-close"
                  onClick={() => setFiltersOpen(false)}
                  aria-label="Close filters"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="lib__filter-sheet-body">
                {sortSelect}
                {filters}
              </div>
              <button
                type="button"
                className="lib__filter-sheet-done"
                onClick={() => setFiltersOpen(false)}
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="lib__filter">
      <div className="lib__bar">
        {searchField}
        {sortSelect}
      </div>
    </div>
  )
}

