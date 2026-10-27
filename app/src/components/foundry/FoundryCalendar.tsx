import { ChevronLeft, ChevronRight, MapPin, Pencil, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  addDays,
  calendarKinds,
  compareEvents,
  formatTimeRange,
  formatWeekRange,
  kindMeta,
  parseLocalDate,
  startOfWeek,
  toIsoDate,
} from '../../lib/academyCalendar'
import {
  createCalendarEvent,
  deleteCalendarEvent,
  listCalendarEvents,
  updateCalendarEvent,
  type CalendarEvent,
  type CalendarEventInput,
  type CalendarEventKind,
} from '../../lib/calendarApi'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'
import { FoundryLoader } from './FoundryLoader'

type EventDraft = {
  title: string
  kind: CalendarEventKind
  event_date: string
  start_time: string
  end_time: string
  location: string
  notes: string
}

type EditorState =
  | { mode: 'closed' }
  | { mode: 'create' }
  | { mode: 'edit'; event: CalendarEvent }

function emptyDraft(date: string, kind: CalendarEventKind = 'class'): EventDraft {
  return { title: '', kind, event_date: date, start_time: '', end_time: '', location: '', notes: '' }
}

function draftFromEvent(event: CalendarEvent): EventDraft {
  return {
    title: event.title,
    kind: event.kind,
    event_date: event.event_date,
    start_time: event.start_time?.slice(0, 5) ?? '',
    end_time: event.end_time?.slice(0, 5) ?? '',
    location: event.location ?? '',
    notes: event.notes ?? '',
  }
}

function draftToInput(draft: EventDraft): CalendarEventInput {
  return {
    title: draft.title.trim(),
    kind: draft.kind,
    event_date: draft.event_date,
    start_time: draft.start_time || null,
    end_time: draft.end_time || null,
    location: draft.location.trim() || null,
    notes: draft.notes.trim() || null,
  }
}

function draftError(draft: EventDraft): string | null {
  if (!draft.title.trim()) return 'Enter a title.'
  if (!draft.event_date) return 'Choose a date.'
  if (draft.start_time && draft.end_time && draft.end_time < draft.start_time) {
    return 'End time must be at or after start time.'
  }
  return null
}

function dayLabel(iso: string): { weekday: string; date: string } {
  const day = parseLocalDate(iso)
  return {
    weekday: day.toLocaleDateString('en-US', { weekday: 'short' }),
    date: day.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }
}

export function FoundryCalendar() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null

  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [reloadToken, setReloadToken] = useState(0)
  const [result, setResult] = useState<{
    key: string
    events: CalendarEvent[]
    error: string | null
  } | null>(null)

  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' })
  const [draft, setDraft] = useState<EventDraft>(() => emptyDraft(toIsoDate(new Date())))
  const [formError, setFormError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [pendingDelete, setPendingDelete] = useState<CalendarEvent | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const rangeStart = toIsoDate(weekStart)
  const rangeEnd = toIsoDate(addDays(weekStart, 6))
  const todayIso = toIsoDate(new Date())
  const isCurrentWeek = rangeStart === toIsoDate(startOfWeek(new Date()))

  const requestKey = workspaceId ? `${workspaceId}:${rangeStart}:${rangeEnd}:${reloadToken}` : null

  useEffect(() => {
    if (!workspaceId || !requestKey) return
    let cancelled = false
    listCalendarEvents(workspaceId, { start: rangeStart, end: rangeEnd })
      .then((rows) => {
        if (!cancelled) setResult({ key: requestKey, events: rows, error: null })
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        const message = caught instanceof Error ? caught.message : 'Could not load the calendar.'
        setResult({ key: requestKey, events: [], error: message })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, requestKey, rangeStart, rangeEnd])

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])
  const events = useMemo(() => [...(result?.events ?? [])].sort(compareEvents), [result])
  const error = result?.error ?? null
  const isLoading = result?.key !== requestKey

  const deadlineCount = useMemo(() => events.filter((event) => event.kind === 'deadline').length, [events])

  const defaultDate = todayIso >= rangeStart && todayIso <= rangeEnd ? todayIso : rangeStart

  const openCreate = () => {
    setDraft(emptyDraft(defaultDate))
    setFormError(null)
    setEditor({ mode: 'create' })
  }

  const openEdit = (event: CalendarEvent) => {
    setDraft(draftFromEvent(event))
    setFormError(null)
    setEditor({ mode: 'edit', event })
  }

  const closeEditor = () => {
    if (isSaving) return
    setEditor({ mode: 'closed' })
  }

  const update = <K extends keyof EventDraft>(key: K, value: EventDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  const handleSave = async (addAnother: boolean) => {
    if (!workspaceId || isSaving || editor.mode === 'closed') return
    const problem = draftError(draft)
    if (problem) {
      setFormError(problem)
      return
    }
    setIsSaving(true)
    setFormError(null)
    try {
      const payload = draftToInput(draft)
      if (editor.mode === 'edit') {
        await updateCalendarEvent(workspaceId, editor.event.id, payload)
      } else {
        await createCalendarEvent(workspaceId, payload)
      }
      if (addAnother) {
        setDraft(emptyDraft(draft.event_date, draft.kind))
      } else {
        setEditor({ mode: 'closed' })
      }
      reload()
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : 'Could not save this event.')
    } finally {
      setIsSaving(false)
    }
  }

  const requestDelete = (event: CalendarEvent) => {
    if (isSaving) return
    setEditor({ mode: 'closed' })
    setDeleteError(null)
    setPendingDelete(event)
  }

  const confirmDelete = async () => {
    if (!workspaceId || !pendingDelete || isDeleting) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await deleteCalendarEvent(workspaceId, pendingDelete.id)
      setPendingDelete(null)
      reload()
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : 'Could not delete this event.')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Academics</div>
          <h2>Calendar</h2>
        </div>
        <span className="as-console__live">
          {events.length} this week · {deadlineCount} due
        </span>
        <button type="button" className="as-console__cta" onClick={openCreate} disabled={!workspaceId}>
          + New event
        </button>
      </header>

      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}

        <div className="as-console__cal-bar">
          <button
            type="button"
            className="as-console__cal-nav"
            onClick={() => setWeekStart((current) => addDays(current, -7))}
            aria-label="Previous week"
          >
            <ChevronLeft size={16} aria-hidden />
          </button>
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost as-console__cal-today"
            onClick={() => setWeekStart(startOfWeek(new Date()))}
            disabled={isCurrentWeek}
          >
            This week
          </button>
          <button
            type="button"
            className="as-console__cal-nav"
            onClick={() => setWeekStart((current) => addDays(current, 7))}
            aria-label="Next week"
          >
            <ChevronRight size={16} aria-hidden />
          </button>
          <h3 className="as-console__cal-range" aria-live="polite">
            {formatWeekRange(weekStart)}
          </h3>
          <p className="as-console__cal-hint">Published to Academy CAL for the platoon.</p>
        </div>

        <section className="as-console__panel">
          {isLoading && events.length === 0 ? (
            <div className="as-console__empty">
              <FoundryLoader label="Loading calendar" size="sm" />
            </div>
          ) : events.length === 0 ? (
            <div className="as-console__empty">
              No events this week. Add a deadline, class, prac app, or evaluation.
            </div>
          ) : (
            <table className="as-console__table as-console__cal-table">
              <thead>
                <tr>
                  <th scope="col">Day</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Event</th>
                  <th scope="col">Time</th>
                  <th scope="col">Location</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((event, index) => {
                  const meta = kindMeta[event.kind]
                  const Icon = meta.icon
                  const label = dayLabel(event.event_date)
                  const isFirstOfDay = event.event_date !== events[index - 1]?.event_date
                  return (
                    <tr
                      key={event.id}
                      className={`${isFirstOfDay ? 'is-day-start' : ''}${event.event_date === todayIso ? ' is-today' : ''}`}
                      onClick={() => openEdit(event)}
                    >
                      <td className="as-console__cal-day">
                        {isFirstOfDay ? (
                          <>
                            <span className="w">{label.weekday}</span>
                            <span className="d">{label.date}</span>
                          </>
                        ) : null}
                      </td>
                      <td>
                        <span className={`as-console__cal-kind ${meta.cls}`}>
                          <Icon size={12} aria-hidden />
                          {meta.chip}
                        </span>
                      </td>
                      <td>
                        <div className="as-console__cal-title">{event.title}</div>
                        {event.notes ? <div className="as-console__cal-notes">{event.notes}</div> : null}
                      </td>
                      <td className="num">{formatTimeRange(event.start_time, event.end_time) ?? '—'}</td>
                      <td>
                        {event.location ? (
                          <span className="as-console__cal-loc">
                            <MapPin size={12} aria-hidden />
                            {event.location}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="as-console__cal-actions">
                        <button
                          type="button"
                          className="as-console__cal-icon"
                          onClick={(click) => {
                            click.stopPropagation()
                            openEdit(event)
                          }}
                          aria-label={`Edit ${event.title}`}
                          title="Edit"
                        >
                          <Pencil size={14} aria-hidden />
                        </button>
                        <button
                          type="button"
                          className="as-console__cal-icon as-console__cal-icon--danger"
                          onClick={(click) => {
                            click.stopPropagation()
                            requestDelete(event)
                          }}
                          aria-label={`Delete ${event.title}`}
                          title="Delete"
                        >
                          <Trash2 size={14} aria-hidden />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <FoundryDialog
        title={editor.mode === 'edit' ? 'Edit event' : 'New event'}
        open={editor.mode !== 'closed'}
        onClose={closeEditor}
      >
        <form
          className="as-console__dialog-form"
          onSubmit={(submit) => {
            submit.preventDefault()
            void handleSave(false)
          }}
        >
          {formError ? <ErrorBanner message={formError} /> : null}

          <label className="as-console__field-label" htmlFor="cal-title">
            Title
          </label>
          <input
            id="cal-title"
            className="as-wiki__input"
            value={draft.title}
            onChange={(change) => update('title', change.target.value)}
            placeholder="TCCC Prac App"
            autoFocus
            disabled={isSaving}
          />

          <div className="as-console__cal-fields">
            <div>
              <label className="as-console__field-label" htmlFor="cal-kind">
                Kind
              </label>
              <select
                id="cal-kind"
                className="as-console__select"
                value={draft.kind}
                onChange={(change) => update('kind', change.target.value as CalendarEventKind)}
                disabled={isSaving}
              >
                {calendarKinds.map((kind) => (
                  <option key={kind} value={kind}>
                    {kindMeta[kind].label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="as-console__field-label" htmlFor="cal-date">
                {draft.kind === 'deadline' ? 'Due date' : 'Date'}
              </label>
              <input
                id="cal-date"
                type="date"
                className="as-wiki__input"
                value={draft.event_date}
                onChange={(change) => update('event_date', change.target.value)}
                disabled={isSaving}
                required
              />
            </div>
          </div>

          <div className="as-console__cal-fields">
            <div>
              <label className="as-console__field-label" htmlFor="cal-start">
                Start time <span className="as-console__cal-optional">optional</span>
              </label>
              <input
                id="cal-start"
                type="time"
                className="as-wiki__input"
                value={draft.start_time}
                onChange={(change) => update('start_time', change.target.value)}
                disabled={isSaving}
              />
            </div>
            <div>
              <label className="as-console__field-label" htmlFor="cal-end">
                End time <span className="as-console__cal-optional">optional</span>
              </label>
              <input
                id="cal-end"
                type="time"
                className="as-wiki__input"
                value={draft.end_time}
                onChange={(change) => update('end_time', change.target.value)}
                disabled={isSaving}
              />
            </div>
          </div>

          <label className="as-console__field-label" htmlFor="cal-location">
            Location <span className="as-console__cal-optional">optional</span>
          </label>
          <input
            id="cal-location"
            className="as-wiki__input"
            value={draft.location}
            onChange={(change) => update('location', change.target.value)}
            placeholder="Cannon Field"
            disabled={isSaving}
          />

          <label className="as-console__field-label" htmlFor="cal-notes">
            Notes <span className="as-console__cal-optional">optional</span>
          </label>
          <textarea
            id="cal-notes"
            className="as-wiki__textarea"
            rows={3}
            value={draft.notes}
            onChange={(change) => update('notes', change.target.value)}
            placeholder="Uniform, what to bring, or submission instructions"
            disabled={isSaving}
          />

          <div className="as-console__dialog-actions">
            {editor.mode === 'edit' ? (
              <button
                type="button"
                className="as-console__cta as-console__cta--ghost as-console__cal-delete"
                onClick={() => requestDelete(editor.event)}
                disabled={isSaving}
              >
                Delete
              </button>
            ) : null}
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              onClick={closeEditor}
              disabled={isSaving}
            >
              Cancel
            </button>
            {editor.mode === 'create' ? (
              <button
                type="button"
                className="as-console__cta as-console__cta--ghost"
                onClick={() => void handleSave(true)}
                disabled={isSaving}
              >
                Save and add another
              </button>
            ) : null}
            <button type="submit" className="as-console__cta" disabled={isSaving}>
              {isSaving ? 'Saving…' : editor.mode === 'edit' ? 'Save changes' : 'Add event'}
            </button>
          </div>
        </form>
      </FoundryDialog>

      <FoundryDialog
        title="Delete event"
        open={pendingDelete !== null}
        onClose={() => {
          if (!isDeleting) setPendingDelete(null)
        }}
      >
        {deleteError ? <ErrorBanner message={deleteError} /> : null}
        <p className="as-console__confirm-copy">
          Delete {pendingDelete ? `"${pendingDelete.title}"` : 'this event'}? It is removed from the
          Academy calendar for everyone.
        </p>
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => setPendingDelete(null)}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button type="button" className="as-console__cta" onClick={() => void confirmDelete()} disabled={isDeleting}>
            {isDeleting ? 'Deleting…' : 'Delete event'}
          </button>
        </div>
      </FoundryDialog>
    </>
  )
}
