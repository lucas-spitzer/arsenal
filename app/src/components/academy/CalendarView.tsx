import { CalendarPlus, ChevronLeft, ChevronRight, Clock, MapPin } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  addDays,
  buildCalendarIcs,
  countByKind,
  formatDateRange,
  formatDayHeading,
  formatTimeRange,
  formatWeekRange,
  groupEventsByDay,
  icsStampFromDate,
  kindMeta,
  parseLocalDate,
  startOfWeek,
  toIsoDate,
  weekDays,
  weekdayShort,
} from '../../lib/academyCalendar'
import {
  clearCalendarTask,
  completeCalendarTask,
  listCalendarEvents,
  type CalendarEvent,
} from '../../lib/calendarApi'
import { FoundryLoader } from '../foundry/FoundryLoader'
import { StudyHead } from './StudySessionChrome'

type CalendarMode = 'schedule' | 'tasks'

type LoadState = {
  key: string
  events: CalendarEvent[]
  error: string | null
}

function KindChip({ event }: { event: CalendarEvent }) {
  const meta = kindMeta[event.kind]
  const Icon = meta.icon
  return (
    <span className={`cal__kind ${meta.cls}`} title={meta.label}>
      <Icon size={12} aria-hidden />
      {meta.chip}
    </span>
  )
}

function EventMeta({ event }: { event: CalendarEvent }) {
  const time = formatTimeRange(event.start_time, event.end_time)
  if (!time && !event.location) return null
  return (
    <div className="cal__event-meta">
      {time && (
        <span>
          <Clock size={12} aria-hidden />
          {time}
        </span>
      )}
      {event.location && (
        <span>
          <MapPin size={12} aria-hidden />
          {event.location}
        </span>
      )}
    </div>
  )
}

function TaskCheck({
  event,
  pending,
  onToggle,
}: {
  event: CalendarEvent
  pending: boolean
  onToggle: (event: CalendarEvent) => void
}) {
  const done = Boolean(event.completed_at)
  return (
    <label className="cal__check">
      <input
        type="checkbox"
        checked={done}
        disabled={pending}
        aria-label={done ? `Mark not done: ${event.title}` : `Mark done: ${event.title}`}
        onChange={() => onToggle(event)}
      />
      {done ? <span>Done</span> : null}
    </label>
  )
}

function EventCard({
  event,
  pending,
  onToggle,
}: {
  event: CalendarEvent
  pending: boolean
  onToggle: (event: CalendarEvent) => void
}) {
  const done = event.kind === 'deadline' && Boolean(event.completed_at)
  return (
    <li className={`cal__event ${kindMeta[event.kind].cls}${done ? ' is-done' : ''}`}>
      <div className="cal__event-top">
        <KindChip event={event} />
        {event.kind === 'deadline' ? (
          <TaskCheck event={event} pending={pending} onToggle={onToggle} />
        ) : null}
      </div>
      <p className="cal__event-title">{event.title}</p>
      <EventMeta event={event} />
      {event.notes && <p className="cal__event-notes">{event.notes}</p>}
    </li>
  )
}

function patchCompleted(events: CalendarEvent[], eventId: string, completedAt: string | null): CalendarEvent[] {
  return events.map((event) => (event.id === eventId ? { ...event, completed_at: completedAt } : event))
}

function downloadIcs(filename: string, body: string) {
  const blob = new Blob([body], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function CalendarView() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const todayIso = toIsoDate(new Date())

  const [mode, setMode] = useState<CalendarMode>('schedule')
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [weekResult, setWeekResult] = useState<LoadState | null>(null)
  const [taskResult, setTaskResult] = useState<LoadState | null>(null)
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(new Set())
  const [taskError, setTaskError] = useState<string | null>(null)

  const rangeStart = toIsoDate(weekStart)
  const rangeEnd = toIsoDate(addDays(weekStart, 6))
  const weekKey = workspaceId ? `${workspaceId}:${rangeStart}:${rangeEnd}` : null
  const taskKey = workspaceId ? `${workspaceId}:deadlines` : null

  useEffect(() => {
    if (!workspaceId || !weekKey) return
    let cancelled = false
    listCalendarEvents(workspaceId, { start: rangeStart, end: rangeEnd })
      .then((rows) => {
        if (!cancelled) setWeekResult({ key: weekKey, events: rows, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Could not load the calendar.'
        setWeekResult({ key: weekKey, events: [], error: message })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, weekKey, rangeStart, rangeEnd])

  useEffect(() => {
    if (!workspaceId || !taskKey) return
    let cancelled = false
    listCalendarEvents(workspaceId, { kind: 'deadline' })
      .then((rows) => {
        if (!cancelled) setTaskResult({ key: taskKey, events: rows, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Could not load tasks.'
        setTaskResult({ key: taskKey, events: [], error: message })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, taskKey])

  const weekEvents = useMemo(() => weekResult?.events ?? [], [weekResult])
  const tasks = useMemo(() => taskResult?.events ?? [], [taskResult])
  const tasksByDay = useMemo(() => groupEventsByDay(tasks), [tasks])
  const days = useMemo(() => weekDays(weekStart), [weekStart])
  const weekByDay = useMemo(() => groupEventsByDay(weekEvents), [weekEvents])
  const counts = countByKind(weekEvents)
  const isCurrentWeek = rangeStart === toIsoDate(startOfWeek(new Date()))
  const rangeLabel = formatDateRange(weekStart, addDays(weekStart, 6))
  const weekLoading = weekResult?.key !== weekKey
  const tasksLoading = taskResult?.key !== taskKey
  const activeResult = mode === 'schedule' ? weekResult : taskResult
  const activeLoading = mode === 'schedule' ? weekLoading : tasksLoading

  const shiftWeek = (delta: number) => setWeekStart((current) => addDays(current, delta * 7))

  const applyCompletion = (eventId: string, completedAt: string | null) => {
    setWeekResult((current) =>
      current ? { ...current, events: patchCompleted(current.events, eventId, completedAt) } : current,
    )
    setTaskResult((current) =>
      current ? { ...current, events: patchCompleted(current.events, eventId, completedAt) } : current,
    )
  }

  const toggleTask = (event: CalendarEvent) => {
    if (!workspaceId || event.kind !== 'deadline' || pendingIds.has(event.id)) return
    const previous = event.completed_at
    setTaskError(null)
    setPendingIds((current) => new Set(current).add(event.id))
    applyCompletion(event.id, previous ? null : new Date().toISOString())
    const request = previous
      ? clearCalendarTask(workspaceId, event.id).then(() => null)
      : completeCalendarTask(workspaceId, event.id).then((updated) => updated.completed_at)
    request
      .then((completedAt) => {
        if (completedAt) applyCompletion(event.id, completedAt)
      })
      .catch((err: unknown) => {
        applyCompletion(event.id, previous)
        setTaskError(err instanceof Error ? err.message : 'Could not update that task.')
      })
      .finally(() => {
        setPendingIds((current) => {
          const next = new Set(current)
          next.delete(event.id)
          return next
        })
      })
  }

  const exportWeek = () => {
    const body = buildCalendarIcs(weekEvents, {
      calendarName: `Arsenal ${rangeLabel}`,
      stamp: icsStampFromDate(new Date()),
    })
    downloadIcs(`schedule-${rangeStart}.ics`, body)
  }

  return (
    <section className="cal study-session" aria-busy={activeLoading}>
      <StudyHead
        eyebrow="Platoon schedule"
        title="Calendar"
        description="The week's events, classes, and tasks. Check off a task when you finish it."
        stats={[
          { value: weekEvents.length, label: 'this week' },
          { value: counts.deadline, label: 'due' },
          { value: counts.prac_app + counts.evaluation, label: 'field' },
        ]}
      />

      <div className="cal__toolbar">
        <div className="cal__nav">
          <button type="button" className="cal__nav-btn" onClick={() => shiftWeek(-1)} aria-label="Previous week">
            <ChevronLeft size={16} aria-hidden />
          </button>
          <button
            type="button"
            className="cal__nav-today"
            onClick={() => setWeekStart(startOfWeek(new Date()))}
            disabled={isCurrentWeek}
          >
            Today
          </button>
          <button type="button" className="cal__nav-btn" onClick={() => shiftWeek(1)} aria-label="Next week">
            <ChevronRight size={16} aria-hidden />
          </button>
          <h2 className="cal__range" aria-live="polite">
            {rangeLabel}
          </h2>
        </div>
        <div className="cal__toolbar-actions">
          <button
            type="button"
            className="cal__export"
            onClick={exportWeek}
            disabled={weekLoading || weekEvents.length === 0}
          >
            <CalendarPlus size={14} aria-hidden />
            Add to Google Calendar
          </button>
          <div className="disc__seg" role="group" aria-label="Calendar layout">
            {(['schedule', 'tasks'] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={`disc__seg-btn${mode === value ? ' is-active' : ''}`}
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
              >
                {value === 'schedule' ? 'Schedule' : 'Tasks'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {taskError ? <p className="cal__task-error">{taskError}</p> : null}

      {activeResult === null && activeLoading ? (
        <div className="lib__empty">
          <FoundryLoader label={mode === 'schedule' ? 'Loading calendar' : 'Loading tasks'} size="sm" />
        </div>
      ) : activeResult?.error ? (
        <div className="lib__empty">
          <p className="lib__empty-title">{mode === 'schedule' ? 'Calendar unavailable' : 'Tasks unavailable'}</p>
          <p className="lib__empty-copy">{activeResult.error}</p>
        </div>
      ) : mode === 'schedule' ? (
        <ol className="cal__week" aria-label={`Week of ${formatWeekRange(weekStart)}`}>
          {days.map((day) => {
            const iso = toIsoDate(day)
            const dayEvents = weekByDay.get(iso) ?? []
            const isToday = iso === todayIso
            const isPast = iso < todayIso
            const classes = [
              'cal__day',
              isToday ? 'is-today' : '',
              isPast ? 'is-past' : '',
              dayEvents.length === 0 ? 'is-empty' : '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <li key={iso} className={classes} aria-current={isToday ? 'date' : undefined}>
                <header className="cal__day-head">
                  <span className="cal__day-name">{weekdayShort(day)}</span>
                  <span className="cal__day-num">{day.getDate()}</span>
                  {isToday ? (
                    <span className="cal__day-tag">Today</span>
                  ) : dayEvents.length > 0 ? (
                    <span className="cal__day-count">
                      {dayEvents.length} {dayEvents.length === 1 ? 'item' : 'items'}
                    </span>
                  ) : null}
                </header>
                {dayEvents.length > 0 ? (
                  <ul className="cal__events">
                    {dayEvents.map((event) => (
                      <EventCard
                        key={event.id}
                        event={event}
                        pending={pendingIds.has(event.id)}
                        onToggle={toggleTask}
                      />
                    ))}
                  </ul>
                ) : (
                  <p className="cal__day-empty">Nothing scheduled</p>
                )}
              </li>
            )
          })}
        </ol>
      ) : tasksByDay.size === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">No tasks</p>
          <p className="lib__empty-copy">Deadlines you can check off will show up here.</p>
        </div>
      ) : (
        <div className="cal__agenda">
          <p className="cal__task-note">Every deadline, not only this week. The arrows still move the schedule.</p>
          {[...tasksByDay.entries()].map(([iso, dayEvents]) => {
            const day = parseLocalDate(iso)
            const isToday = iso === todayIso
            return (
              <section
                key={iso}
                className={`cal__agenda-day${iso < todayIso ? ' is-past' : ''}${isToday ? ' is-today' : ''}`}
                aria-label={formatDayHeading(day)}
              >
                <div className="lib__band">
                  <h3 className="lib__band-title">{formatDayHeading(day)}</h3>
                  {isToday && <span className="cal__day-tag">Today</span>}
                  <span className="lib__band-line" />
                  <span className="lib__band-count">
                    {dayEvents.length} {dayEvents.length === 1 ? 'task' : 'tasks'}
                  </span>
                </div>
                <ul className="cal__tasks">
                  {dayEvents.map((event) => {
                    const done = Boolean(event.completed_at)
                    const due =
                      formatTimeRange(event.start_time, event.end_time) ??
                      (event.kind === 'deadline' ? 'Due EOD' : 'All day')
                    return (
                      <li key={event.id} className={`cal__task${done ? ' is-done' : ''}`}>
                        <TaskCheck event={event} pending={pendingIds.has(event.id)} onToggle={toggleTask} />
                        <div className="cal__row-body">
                          <p className="cal__event-title">{event.title}</p>
                          {event.notes && <p className="cal__event-notes">{event.notes}</p>}
                        </div>
                        <span className="cal__row-time">{due}</span>
                      </li>
                    )
                  })}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </section>
  )
}
