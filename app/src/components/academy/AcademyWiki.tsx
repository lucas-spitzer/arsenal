import { Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  deprecateWikiEntry,
  reviseWikiEntry,
  updateWikiEntry,
} from '../../lib/wikiApi'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import type { Source, WikiEntry, WikiListItem } from '../../lib/workspaceApi'
import { StudyHead } from './StudySessionChrome'

const ENTRY_KINDS = ['term', 'list', 'elo', 'abbreviation', 'compare'] as const
const IMPORTANCE_LEVELS = ['essential', 'supporting', 'contextual'] as const

function asEntryKind(value: string): (typeof ENTRY_KINDS)[number] {
  if (
    value === 'list' ||
    value === 'elo' ||
    value === 'abbreviation' ||
    value === 'compare'
  ) {
    return value
  }
  return 'term'
}

function uploadLabel(origin: Record<string, unknown>): string {
  const value = origin.section_title
  return typeof value === 'string' ? value.trim() : ''
}

function citedPassage(origin: Record<string, unknown>): string {
  const value = origin.passage
  return typeof value === 'string' ? value.trim() : ''
}

function citedSourceName(origin: Record<string, unknown>, sources: Source[]): string {
  const section = uploadLabel(origin)
  if (section) return section
  const sourceId = typeof origin.source_id === 'string' ? origin.source_id : null
  if (!sourceId) return ''
  const source = sources.find((item) => item.id === sourceId)
  return source ? sourceDisplayName(source) : ''
}

function KindPill({ value }: { value: string }) {
  return <span className={`academy-wiki__pill academy-wiki__pill--${value}`}>{value}</span>
}

function entryHasDetail(entry: WikiEntry): boolean {
  if (entry.definition.trim()) return true
  if (entry.significance?.trim()) return true
  return (entry.items ?? []).length > 0
}

function EntryDetail({ entry }: { entry: WikiEntry }) {
  const items = entry.items ?? []
  return (
    <>
      {entry.category ? <div className="academy-wiki__category">{entry.category}</div> : null}
      {entry.definition}
      {entry.significance ? <p className="academy-wiki__significance">{entry.significance}</p> : null}
      {entry.entry_kind === 'list' && items.length > 0 ? (
        <ol className="academy-wiki__items">
          {items.map((item) => (
            <li key={item.name}>
              <strong>{item.name}</strong>
              {item.details ? <span> — {item.details}</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {entry.entry_kind === 'compare' && items.length > 0 ? (
        <ol className="academy-wiki__items">
          {items.map((item) => {
            const poles = entry.aliases.map((alias) => alias.trim()).filter(Boolean)
            const left = poles[0] ?? 'A'
            const right = poles[1] ?? 'B'
            return (
              <li key={item.name}>
                <strong>{item.name}</strong>
                {item.a && item.b ? (
                  <span>
                    {' '}
                    — {left}: {item.a} · {right}: {item.b}
                  </span>
                ) : null}
              </li>
            )
          })}
        </ol>
      ) : null}
    </>
  )
}

function EntryDialog({
  entry,
  sourceName,
  passage,
  readerLink,
  onClose,
}: {
  entry: WikiEntry
  sourceName: string
  passage: string
  readerLink: string | null
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = `academy-wiki-dialog-${entry.id}`

  useEffect(() => {
    panelRef.current?.focus()
  }, [entry.id])

  useEffect(() => {
    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return createPortal(
    <div className="academy-wiki__dialog-backdrop" onClick={onClose} role="presentation">
      <div
        ref={panelRef}
        className="academy-wiki__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(click) => click.stopPropagation()}
      >
        <div className="academy-wiki__dialog-head">
          <button type="button" className="academy-wiki__dialog-close" onClick={onClose}>
            Close
          </button>
        </div>
        <h3 id={titleId} className="academy-wiki__dialog-title">
          {entry.preferred_label}
        </h3>
        <dl className="academy-wiki__dialog-facts">
          <div>
            <dt>Kind</dt>
            <dd>
              <KindPill value={entry.entry_kind} />
            </dd>
          </div>
          {sourceName ? (
            <div>
              <dt>Source</dt>
              <dd>{sourceName}</dd>
            </div>
          ) : null}
          {passage ? (
            <div>
              <dt>Passage</dt>
              <dd>{passage}</dd>
            </div>
          ) : null}
        </dl>
        <div className="academy-wiki__definition">
          <EntryDetail entry={entry} />
        </div>
        {readerLink ? (
          <a
            href={readerLink}
            target="_blank"
            rel="noreferrer"
            className="academy-wiki__reader-link"
          >
            Open passage
          </a>
        ) : null}
      </div>
    </div>,
    document.body,
  )
}

function EntryRow({
  entry,
  canEdit,
  detailInDialog,
  onChanged,
  onEditingChange,
  startEditing = false,
}: {
  entry: WikiEntry
  canEdit: boolean
  detailInDialog: boolean
  onChanged: () => Promise<void>
  onEditingChange: (editing: boolean) => void
  startEditing?: boolean
}) {
  const { activeWorkspace } = useWorkspace()
  const { sources } = useWorkspaceData()
  const [isEditing, setIsEditing] = useState(canEdit && startEditing)
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
  const [detailOpen, setDetailOpen] = useState(false)
  const moreRef = useRef<HTMLButtonElement>(null)

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
                .map((item) => ({
                  name: item.name.trim(),
                  details: (item.details ?? '').trim(),
                }))
                .filter((item) => item.name)
            : kind === 'compare'
              ? items
                  .map((item) => ({
                    name: item.name.trim(),
                    a: (item.a ?? '').trim(),
                    b: (item.b ?? '').trim(),
                  }))
                  .filter((item) => item.name && item.a && item.b)
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

  const readerLink = entry.evidence.find((record) => record.reader_link)?.reader_link ?? null
  const sourceName = citedSourceName(entry.origin, sources)
  const passage = citedPassage(entry.origin)
  const showDetail = detailInDialog && entryHasDetail(entry)
  const columnCount = detailInDialog ? 4 : 6

  const closeDetail = () => {
    setDetailOpen(false)
    moreRef.current?.focus()
  }

  if (canEdit && isEditing) {
    return (
      <tr className="academy-wiki__row academy-wiki__row--edit">
        <td colSpan={columnCount}>
          <div className="academy-wiki__edit">
            {sourceName || passage || readerLink ? (
              <p className="academy-wiki__citation">
                {sourceName}
                {readerLink ? (
                  <>
                    {' '}
                    <a
                      href={readerLink}
                      target="_blank"
                      rel="noreferrer"
                      className="academy-wiki__reader-link"
                    >
                      Open passage
                    </a>
                  </>
                ) : null}
                {passage ? <span className="academy-wiki__citation-passage">{passage}</span> : null}
              </p>
            ) : null}
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
              aria-label={kind === 'list' || kind === 'compare' ? 'Overview' : 'Definition'}
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
                      value={item.details ?? ''}
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
            {kind === 'compare' ? (
              <div className="academy-wiki__items-edit">
                {items.map((item, index) => (
                  <div className="academy-wiki__item-edit" key={index}>
                    <input
                      className="academy-wiki__input"
                      value={item.name}
                      aria-label={`Diff ${index + 1} dimension`}
                      placeholder="Dimension"
                      onChange={(event) => {
                        const name = event.target.value
                        setItems((current) =>
                          current.map((row, rowIndex) => (rowIndex === index ? { ...row, name } : row)),
                        )
                      }}
                    />
                    <input
                      className="academy-wiki__input"
                      value={item.a ?? ''}
                      aria-label={`Diff ${index + 1} pole a`}
                      placeholder="Pole A"
                      onChange={(event) => {
                        const a = event.target.value
                        setItems((current) =>
                          current.map((row, rowIndex) => (rowIndex === index ? { ...row, a } : row)),
                        )
                      }}
                    />
                    <input
                      className="academy-wiki__input"
                      value={item.b ?? ''}
                      aria-label={`Diff ${index + 1} pole b`}
                      placeholder="Pole B"
                      onChange={(event) => {
                        const b = event.target.value
                        setItems((current) =>
                          current.map((row, rowIndex) => (rowIndex === index ? { ...row, b } : row)),
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
                  onClick={() => setItems((current) => [...current, { name: '', a: '', b: '' }])}
                >
                  Add diff
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
        {!detailInDialog && readerLink ? (
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
      {detailInDialog ? null : (
        <td className="academy-wiki__definition" colSpan={2}>
          <EntryDetail entry={entry} />
        </td>
      )}
      <td className="academy-wiki__kind">
        <KindPill value={entry.entry_kind} />
      </td>
      <td className="academy-wiki__source">
        {sourceName}
        {passage ? <span className="academy-wiki__passage">{passage}</span> : null}
      </td>
      {detailInDialog || canEdit ? (
        <td className="academy-wiki__row-actions">
          <div className="academy-wiki__actions">
            {showDetail ? (
              <button
                ref={moreRef}
                type="button"
                className="academy-wiki__action"
                onClick={() => setDetailOpen(true)}
                aria-label={`More about ${entry.preferred_label}`}
              >
                More
              </button>
            ) : null}
            {canEdit ? (
              <>
                <button
                  type="button"
                  className="academy-wiki__action academy-wiki__action--edit"
                  disabled={isBusy}
                  onClick={() => {
                    setDetailOpen(false)
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
              </>
            ) : null}
          </div>
          {error ? <p className="academy-wiki__error">{error}</p> : null}
          {detailOpen ? (
            <EntryDialog
              entry={entry}
              sourceName={sourceName}
              passage={passage}
              readerLink={readerLink}
              onClose={closeDetail}
            />
          ) : null}
        </td>
      ) : null}
    </tr>
  )
}

export function AcademyWiki({
  sourceId = null,
  targetId = null,
  wikiKind = null,
}: {
  sourceId?: string | null
  targetId?: string | null
  wikiKind?: 'elo' | null
}) {
  const { wikiEntries, sources, isLoading, error, refresh } = useWorkspaceData()
  const { approvedUser } = useAuth()
  const canEdit = isAdminAccess(approvedUser?.role)
  const [query, setQuery] = useState('')
  const [isEditing, setIsEditing] = useState(() => canEdit && Boolean(targetId))

  const elosOnly = wikiKind === 'elo'
  const visibleEntries = useMemo(() => {
    const q = query.toLowerCase()
    return wikiEntries.filter((entry) => {
      if (entry.status === 'deprecated') return false
      if (elosOnly ? entry.entry_kind !== 'elo' : entry.entry_kind === 'elo') return false
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
        !entry.definition.toLowerCase().includes(q) &&
        !uploadLabel(entry.origin).toLowerCase().includes(q) &&
        !citedSourceName(entry.origin, sources).toLowerCase().includes(q) &&
        !citedPassage(entry.origin).toLowerCase().includes(q)
      ) {
        return false
      }
      return true
    })
  }, [wikiEntries, sources, query, sourceId, targetId, elosOnly])

  return (
    <section className="study-session academy-wiki">
      <StudyHead
        eyebrow="Academy"
        title={elosOnly ? 'ELOs' : 'Wiki'}
        description={
          elosOnly
            ? 'Enabling learning objectives for this source.'
            : canEdit
              ? 'Edit, deprecate, or rewrite canonical entries. Produce new ones with Wiki Knowledge on a New Run.'
              : 'Canonical entries for the platoon.'
        }
        stats={[{ value: visibleEntries.length, label: 'entries' }]}
      />

      {error ? <p className="academy-wiki__error">{error}</p> : null}

      {isEditing ? null : (
        <div className="lib__search academy-wiki__search">
          <Search size={16} aria-hidden="true" />
          <input
            placeholder={elosOnly ? 'Search ELOs…' : 'Search wiki entries…'}
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
            {query ? 'No matching entries' : elosOnly ? 'No ELOs for this source' : 'No wiki entries yet'}
          </p>
          <p className="lib__empty-copy">
            {query
              ? 'Adjust the search, or open a different entry from Library.'
              : elosOnly
                ? 'Knowledge ELOs for a book show up here after they are imported.'
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
            <table className={elosOnly ? 'academy-wiki__table academy-wiki__table--elo' : 'academy-wiki__table'}>
              <thead>
                <tr>
                  <th>Label</th>
                  {elosOnly ? null : <th colSpan={2}>Definition</th>}
                  <th>Kind</th>
                  <th>Source</th>
                  {elosOnly || canEdit ? <th>{canEdit ? 'Actions' : <span className="sr-only">Details</span>}</th> : null}
                </tr>
              </thead>
              <tbody>
                {visibleEntries.map((entry) => (
                  <EntryRow
                    key={entry.id}
                    entry={entry}
                    canEdit={canEdit}
                    detailInDialog={elosOnly}
                    onChanged={refresh}
                    onEditingChange={setIsEditing}
                    startEditing={canEdit && entry.id === targetId}
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
