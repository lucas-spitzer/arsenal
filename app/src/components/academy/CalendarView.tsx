import { ChevronLeft, ChevronRight, Clock, MapPin } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  addDays,
  countByKind,
  formatDateRange,
  formatDayHeading,
  formatTimeRange,
  formatWeekRange,
  groupEventsByDay,
  kindMeta,
  parseLocalDate,
  startOfWeek,
  toIsoDate,
  weekDays,
  weekdayShort,
} from '../../lib/academyCalendar'
import { listCalendarEvents, type CalendarEvent } from '../../lib/calendarApi'
import { FoundryLoader } from '../foundry/FoundryLoader'
import { StudyHead } from './StudySessionChrome'

type CalendarMode = 'week' | 'agenda'

const AGENDA_WEEKS = 4

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

function EventCard({ event }: { event: CalendarEvent }) {
  return (
    <li className={`cal__event ${kindMeta[event.kind].cls}`}>
      <KindChip event={event} />
      <p className="cal__event-title">{event.title}</p>
      <EventMeta event={event} />
      {event.notes && <p className="cal__event-notes">{event.notes}</p>}
    </li>
  )
}

export function CalendarView() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const todayIso = toIsoDate(new Date())

  const [mode, setMode] = useState<CalendarMode>('week')
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [result, setResult] = useState<{
    key: string
    events: CalendarEvent[]
    error: string | null
  } | null>(null)

  const rangeDays = mode === 'week' ? 7 : AGENDA_WEEKS * 7
  const rangeStart = toIsoDate(weekStart)
  const rangeEnd = toIsoDate(addDays(weekStart, rangeDays - 1))
  const requestKey = workspaceId ? `${workspaceId}:${rangeStart}:${rangeEnd}` : null

  useEffect(() => {
    if (!workspaceId || !requestKey) return
    let cancelled = false
    listCalendarEvents(workspaceId, { start: rangeStart, end: rangeEnd })
      .then((rows) => {
        if (!cancelled) setResult({ key: requestKey, events: rows, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Could not load the calendar.'
        setResult({ key: requestKey, events: [], error: message })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, requestKey, rangeStart, rangeEnd])

  const events = useMemo(() => result?.events ?? [], [result])
  const error = result?.error ?? null
  const hasLoaded = result !== null
  const isLoading = result?.key !== requestKey

  const byDay = useMemo(() => groupEventsByDay(events), [events])
  const days = useMemo(() => weekDays(weekStart), [weekStart])
  const weekEvents = useMemo(() => {
    const weekEnd = toIsoDate(addDays(weekStart, 6))
    return events.filter((event) => event.event_date >= rangeStart && event.event_date <= weekEnd)
  }, [events, weekStart, rangeStart])
  const counts = countByKind(weekEvents)
  const isCurrentWeek = rangeStart === toIsoDate(startOfWeek(new Date()))

  const rangeLabel = formatDateRange(weekStart, addDays(weekStart, rangeDays - 1))

  const shiftWeek = (delta: number) => setWeekStart((current) => addDays(current, delta * 7))

  return (
    <section className="cal study-session" aria-busy={isLoading}>
      <StudyHead
        eyebrow="Academic schedule"
        title="Calendar"
        description="Deadlines, classes, practical applications, and evaluations for the platoon, posted by the Academics officer."
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
        <div className="disc__seg" role="group" aria-label="Calendar layout">
          {(['week', 'agenda'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`disc__seg-btn${mode === value ? ' is-active' : ''}`}
              aria-pressed={mode === value}
              onClick={() => setMode(value)}
            >
              {value === 'week' ? 'Week' : 'Agenda'}
            </button>
          ))}
        </div>
      </div>

      {!hasLoaded && isLoading ? (
        <div className="lib__empty">
          <FoundryLoader label="Loading calendar" size="sm" />
        </div>
      ) : error ? (
        <div className="lib__empty">
          <p className="lib__empty-title">Calendar unavailable</p>
          <p className="lib__empty-copy">{error}</p>
        </div>
      ) : mode === 'week' ? (
        <ol className="cal__week" aria-label={`Week of ${formatWeekRange(weekStart)}`}>
          {days.map((day) => {
            const iso = toIsoDate(day)
            const dayEvents = byDay.get(iso) ?? []
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
                      <EventCard key={event.id} event={event} />
                    ))}
                  </ul>
                ) : (
                  <p className="cal__day-empty">Nothing scheduled</p>
                )}
              </li>
            )
          })}
        </ol>
      ) : byDay.size === 0 ? (
        <div className="lib__empty">
          <p className="lib__empty-title">Nothing scheduled</p>
          <p className="lib__empty-copy">No deadlines, classes, or prac apps are posted for these four weeks.</p>
        </div>
      ) : (
        <div className="cal__agenda">
          {[...byDay.entries()].map(([iso, dayEvents]) => {
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
                    {dayEvents.length} {dayEvents.length === 1 ? 'item' : 'items'}
                  </span>
                </div>
                <ul className="cal__rows">
                  {dayEvents.map((event) => (
                    <li key={event.id} className={`cal__row ${kindMeta[event.kind].cls}`}>
                      <span className="cal__row-time">
                        {formatTimeRange(event.start_time, event.end_time) ??
                          (event.kind === 'deadline' ? 'Due EOD' : 'All day')}
                      </span>
                      <div className="cal__row-body">
                        <p className="cal__event-title">{event.title}</p>
                        {event.location && (
                          <div className="cal__event-meta">
                            <span>
                              <MapPin size={12} aria-hidden />
                              {event.location}
                            </span>
                          </div>
                        )}
                        {event.notes && <p className="cal__event-notes">{event.notes}</p>}
                      </div>
                      <KindChip event={event} />
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </section>
  )
}
