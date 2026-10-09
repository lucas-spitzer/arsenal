import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  deprecateWikiEntry,
  reviseWikiEntry,
  updateWikiEntry,
} from '../../lib/wikiApi'
import type { WikiEntry, WikiListItem } from '../../lib/workspaceApi'
import { StudyHead } from './StudySessionChrome'

const ENTRY_KINDS = ['term', 'list'] as const
const IMPORTANCE_LEVELS = ['essential', 'supporting', 'contextual'] as const

function asEntryKind(value: string): (typeof ENTRY_KINDS)[number] {
  return value === 'list' ? 'list' : 'term'
}

function KindPill({ value }: { value: string }) {
  return <span className={`academy-wiki__pill academy-wiki__pill--${value}`}>{value}</span>
}

function EntryRow({
  entry,
  onChanged,
  onEditingChange,
  startEditing = false,
}: {
  entry: WikiEntry
  onChanged: () => Promise<void>
  onEditingChange: (editing: boolean) => void
  startEditing?: boolean
}) {
  const { activeWorkspace } = useWorkspace()
  const [isEditing, setIsEditing] = useState(startEditing)
  const [label, setLabel] = useState(entry.preferred_label)
  const [definition, setDefinition] = useState(entry.definition)
  const [significance, setSignificance] = useState(entry.significance ?? '')
  const [category, setCategory] = useState(entry.category ?? '')
  const [items, setItems] = useState<WikiListItem[]>(entry.items ?? [])
  const [kind, setKind] = useState(asEntryKind(entry.entry_kind))
  const [importance, setImportance] = useState(entry.importance)
  const [aliases, setAliases] = useState(entry.aliases.join(', '))
  const [instruction, setInstruction] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    if (!activeWorkspace) return
    setIsBusy(true)
    setError(null)
    try {
      await updateWikiEntry(activeWorkspace.id, entry.id, {
        preferred_label: label,
        definition,
        significance: significance.trim() || null,
        category: category.trim() || null,
        items:
          kind === 'list'
            ? items
                .map((item) => ({ name: item.name.trim(), details: item.details.trim() }))
                .filter((item) => item.name)
            : [],
        entry_kind: kind,
        importance,
        aliases: aliases
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      })
      await onChanged()
      setIsEditing(false)
      onEditingChange(false)
      setInstruction('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save entry.')
    } finally {
      setIsBusy(false)
    }
  }

  const rewrite = async () => {
    if (!activeWorkspace) return
    if (!instruction.trim()) {
      setError('Describe how to rewrite the definition.')
      return
    }
    setIsBusy(true)
    setError(null)
    try {
      const proposal = await reviseWikiEntry(activeWorkspace.id, entry.id, instruction.trim())
      setDefinition(proposal.definition)
      if (proposal.preferred_label) setLabel(proposal.preferred_label)
      if (proposal.aliases) setAliases(proposal.aliases.join(', '))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to rewrite definition.')
    } finally {
      setIsBusy(false)
    }
  }

  const deprecate = async () => {
    if (!activeWorkspace) return
    setIsBusy(true)
    setError(null)
    try {
      await deprecateWikiEntry(activeWorkspace.id, entry.id)
      await onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to deprecate entry.')
    } finally {
      setIsBusy(false)
    }
  }

  if (isEditing) {
    return (
      <tr className="academy-wiki__row academy-wiki__row--edit">
        <td colSpan={6}>
          <div className="academy-wiki__edit">
            <input
              className="academy-wiki__input academy-wiki__input--label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              aria-label="Preferred label"
            />
            <textarea
              className="academy-wiki__textarea academy-wiki__textarea--definition"
              rows={4}
              value={definition}
              onChange={(event) => setDefinition(event.target.value)}
              aria-label={kind === 'list' ? 'Overview' : 'Definition'}
            />
            <textarea
              className="academy-wiki__textarea"
              rows={2}
              value={significance}
              onChange={(event) => setSignificance(event.target.value)}
              aria-label="Significance"
              placeholder="Why it matters"
            />
            <input
              className="academy-wiki__input"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              aria-label="Category"
              placeholder="Category"
            />
            {kind === 'list' ? (
              <div className="academy-wiki__items-edit">
                {items.map((item, index) => (
                  <div className="academy-wiki__item-edit" key={index}>
                    <input
                      className="academy-wiki__input"
                      value={item.name}
                      aria-label={`Item ${index + 1} name`}
                      placeholder="Name"
                      onChange={(event) => {
                        const name = event.target.value
                        setItems((current) =>
                          current.map((row, rowIndex) => (rowIndex === index ? { ...row, name } : row)),
                        )
                      }}
                    />
                    <input
                      className="academy-wiki__input"
                      value={item.details}
                      aria-label={`Item ${index + 1} details`}
                      placeholder="Details"
                      onChange={(event) => {
                        const details = event.target.value
                        setItems((current) =>
                          current.map((row, rowIndex) => (rowIndex === index ? { ...row, details } : row)),
                        )
                      }}
                    />
                    <button
                      type="button"
                      className="academy-wiki__action academy-wiki__action--cancel"
                      onClick={() => setItems((current) => current.filter((_, rowIndex) => rowIndex !== index))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="academy-wiki__action"
                  onClick={() => setItems((current) => [...current, { name: '', details: '' }])}
                >
                  Add item
                </button>
              </div>
            ) : null}
            <div className="academy-wiki__edit-row">
              <label className="academy-wiki__select">
                <span>Kind</span>
                <select value={kind} onChange={(event) => setKind(asEntryKind(event.target.value))}>
                  {ENTRY_KINDS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="academy-wiki__select">
                <span>Importance</span>
                <select
                  value={importance}
                  onChange={(event) => setImportance(event.target.value)}
                >
                  {IMPORTANCE_LEVELS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <input
                className="academy-wiki__input"
                placeholder="Aliases, comma-separated"
                value={aliases}
                onChange={(event) => setAliases(event.target.value)}
                aria-label="Aliases"
              />
            </div>
            <label className="academy-wiki__rewrite">
              <span>Rewrite instruction</span>
              <textarea
                className="academy-wiki__textarea"
                rows={2}
                placeholder="Make this tighter for a flashcard. Do not add facts."
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
              />
            </label>
            {error ? <p className="academy-wiki__error">{error}</p> : null}
            <div className="academy-wiki__actions">
              <button
                type="button"
                className="academy-wiki__action academy-wiki__action--rewrite"
                disabled={isBusy}
                onClick={() => void rewrite()}
              >
                Rewrite
              </button>
              <button
                type="button"
                className="academy-wiki__action academy-wiki__action--save"
                disabled={isBusy}
                onClick={() => void save()}
              >
                Save
              </button>
              <button
                type="button"
                className="academy-wiki__action academy-wiki__action--cancel"
                disabled={isBusy}
                onClick={() => {
                  setIsEditing(false)
                  onEditingChange(false)
                  setLabel(entry.preferred_label)
                  setDefinition(entry.definition)
                  setSignificance(entry.significance ?? '')
                  setCategory(entry.category ?? '')
                  setItems(entry.items ?? [])
                  setKind(asEntryKind(entry.entry_kind))
                  setImportance(entry.importance)
                  setAliases(entry.aliases.join(', '))
                  setInstruction('')
                  setError(null)
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </td>
      </tr>
    )
  }

  const readerLink = entry.evidence.find((record) => record.reader_link)?.reader_link ?? null

  return (
    <tr
      className={
        entry.status !== 'canonical'
          ? 'academy-wiki__row academy-wiki__row--muted'
          : 'academy-wiki__row'
      }
    >
      <td className="academy-wiki__label">
        {entry.preferred_label}
        {readerLink ? (
          <>
            {' '}
            <a
              href={readerLink}
              target="_blank"
              rel="noreferrer"
              className="academy-wiki__reader-link"
              title="Open the cited passage in the Reader"
            >
              ↗
            </a>
          </>
        ) : null}
      </td>
      <td className="academy-wiki__definition" colSpan={2}>
        {entry.category ? <div className="academy-wiki__category">{entry.category}</div> : null}
        {entry.definition}
        {entry.significance ? <p className="academy-wiki__significance">{entry.significance}</p> : null}
        {entry.entry_kind === 'list' && entry.items?.length ? (
          <ol className="academy-wiki__items">
            {entry.items.map((item) => (
              <li key={item.name}>
                <strong>{item.name}</strong>
                {item.details ? <span> — {item.details}</span> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </td>
      <td>
        <KindPill value={entry.entry_kind} />
      </td>
      <td className="academy-wiki__importance">{entry.importance}</td>
      <td>
        <div className="academy-wiki__actions">
          <button
            type="button"
            className="academy-wiki__action academy-wiki__action--edit"
            disabled={isBusy}
            onClick={() => {
              setIsEditing(true)
              onEditingChange(true)
            }}
          >
            Edit
          </button>
          {entry.status === 'canonical' ? (
            <button
              type="button"
              className="academy-wiki__action academy-wiki__action--deprecate"
              disabled={isBusy}
              onClick={() => void deprecate()}
              title="Soft delete: the entry stops feeding assessments and the assistant"
            >
              Deprecate
            </button>
          ) : (
            <span className="academy-wiki__pill">{entry.status}</span>
          )}
        </div>
        {error ? <p className="academy-wiki__error">{error}</p> : null}
      </td>
    </tr>
  )
}

export function AcademyWiki({
  sourceId = null,
  targetId = null,
}: {
  sourceId?: string | null
  targetId?: string | null
}) {
  const { wikiEntries, isLoading, error, refresh } = useWorkspaceData()
  const [query, setQuery] = useState('')
  const [isEditing, setIsEditing] = useState(() => Boolean(targetId))

  const visibleEntries = useMemo(() => {
    const q = query.toLowerCase()
    return wikiEntries.filter((entry) => {
      if (entry.status === 'deprecated') return false
      if (targetId) return entry.id === targetId
      if (sourceId) {
        const origin = entry.origin
        const originSource =
          origin && typeof origin.source_id === 'string' ? origin.source_id : null
        const evidenceSource = entry.evidence[0]?.source_id ?? null
        if (originSource !== sourceId && evidenceSource !== sourceId) return false
      }
      if (
        q &&
        !entry.preferred_label.toLowerCase().includes(q) &&
        !entry.definition.toLowerCase().includes(q)
      ) {
        return false
      }
      return true
    })
  }, [wikiEntries, query, sourceId, targetId])

  return (
    <section className="study-session academy-wiki">
      <StudyHead
        eyebrow="Academy"
        title="Wiki"
        description="Edit, deprecate, or rewrite canonical entries. Produce new ones with Wiki Knowledge on a New Run."
        stats={[{ value: visibleEntries.length, label: 'entries' }]}
      />

      {error ? <p className="academy-wiki__error">{error}</p> : null}

      {isEditing ? null : (
        <div className="lib__search academy-wiki__search">
          <Search size={16} aria-hidden="true" />
          <input
            placeholder="Search wiki entries…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search wiki entries"
          />
        </div>
      )}

      {isLoading && wikiEntries.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">Loading wiki</p>
          <p className="lib__empty-copy">Fetching canonical entries for this workspace.</p>
        </div>
      ) : visibleEntries.length === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">
            {query ? 'No matching entries' : 'No wiki entries yet'}
          </p>
          <p className="lib__empty-copy">
            {query
              ? 'Adjust the search, or open a different entry from Library.'
              : 'Run Wiki Knowledge from Foundry OPS, then open an entry from Library.'}
          </p>
        </div>
      ) : (
        <section className="academy-wiki__panel">
          <div className="academy-wiki__panel-head">
            <h2>Entries</h2>
            <span className="academy-wiki__count">{visibleEntries.length}</span>
          </div>
          <div className="academy-wiki__table-wrap">
            <table className="academy-wiki__table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th colSpan={2}>Definition</th>
                  <th>Kind</th>
                  <th>Importance</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleEntries.map((entry) => (
                  <EntryRow
                    key={entry.id}
                    entry={entry}
                    onChanged={refresh}
                    onEditingChange={setIsEditing}
                    startEditing={entry.id === targetId}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  )
}
