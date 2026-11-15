import type { LucideIcon } from 'lucide-react'
import { AlarmClock, CalendarClock, ClipboardCheck, Compass, Presentation } from 'lucide-react'
import type { CalendarEvent, CalendarEventKind } from './calendarApi'

export type CalendarKindMeta = {
  label: string
  /** Short label for chips and the "Due" marker on deadlines. */
  chip: string
  icon: LucideIcon
  cls: string
}

export const calendarKinds: CalendarEventKind[] = ['schedule', 'class', 'prac_app', 'evaluation', 'deadline']

export const kindMeta: Record<CalendarEventKind, CalendarKindMeta> = {
  schedule: { label: 'Schedule', chip: 'Schedule', icon: CalendarClock, cls: 'cal__kind--schedule' },
  class: { label: 'Class', chip: 'Class', icon: Presentation, cls: 'cal__kind--class' },
  prac_app: { label: 'Practical application', chip: 'Prac app', icon: Compass, cls: 'cal__kind--prac' },
  evaluation: { label: 'Evaluation', chip: 'Eval', icon: ClipboardCheck, cls: 'cal__kind--eval' },
  deadline: { label: 'Deadline', chip: 'Due EOD', icon: AlarmClock, cls: 'cal__kind--due' },
}

const pad = (value: number) => String(value).padStart(2, '0')

/** `YYYY-MM-DD` for the local calendar day, never shifted through UTC. */
export function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Reads a `YYYY-MM-DD` value as local midnight. `new Date('2026-10-25')` would be UTC. */
export function parseLocalDate(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  return new Date(year, (month ?? 1) - 1, day ?? 1)
}

export function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

/** Weeks start on Sunday. */
export function startOfWeek(date: Date): Date {
  return addDays(new Date(date.getFullYear(), date.getMonth(), date.getDate()), -date.getDay())
}

export function weekDays(weekStart: Date): Date[] {
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index))
}

const COURSE_CODE = /^((?:BS|B)\d+)\s+(.+)$/
const ODT_DEADLINE = 'Read Range Week SPINS'
const HIKE_BACK = 'Hike to McGlothlin Hall'
/** Sort-only clock for the untimed Friday hike, after the range and before de-issue. */
const HIKE_BACK_SORT_TIME = '11:59:59'

/** A leading course code such as `B023029` or `BS230009` becomes the dialog ID. */
export function eventIdentity(title: string): { id: string | null; title: string } {
  const match = title.match(COURSE_CODE)
  if (!match?.[1] || !match[2]) return { id: null, title }
  return { id: match[1], title: match[2] }
}

export function chipLabel(event: Pick<CalendarEvent, 'kind' | 'title'>): string {
  if (event.kind === 'deadline' && event.title === ODT_DEADLINE) return 'Due ODT'
  return kindMeta[event.kind].chip
}

/** Clock time, or the due mark for a deadline that has no clock time. */
export function eventTimeLabel(
  event: Pick<CalendarEvent, 'kind' | 'title' | 'start_time' | 'end_time'>,
): string | null {
  if (event.kind === 'deadline' && event.title === ODT_DEADLINE) return 'Due ODT'
  const range = formatTimeRange(event.start_time, event.end_time)
  if (range) return range
  if (event.kind === 'deadline') return 'Due EOD'
  return null
}

function sortTime(event: CalendarEvent): string | null {
  if (event.start_time == null && event.end_time == null && event.title === HIKE_BACK) {
    return HIKE_BACK_SORT_TIME
  }
  return event.start_time
}

export function compareEvents(a: CalendarEvent, b: CalendarEvent): number {
  if (a.event_date !== b.event_date) return a.event_date < b.event_date ? -1 : 1
  const aTime = sortTime(a)
  const bTime = sortTime(b)
  if (aTime !== bTime) {
    if (aTime == null) return -1
    if (bTime == null) return 1
    return aTime < bTime ? -1 : 1
  }
  return a.title.localeCompare(b.title)
}

/** Events keyed by `YYYY-MM-DD`, each day sorted with untimed items first. */
export function groupEventsByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const grouped = new Map<string, CalendarEvent[]>()
  for (const event of [...events].sort(compareEvents)) {
    const day = event.event_date.slice(0, 10)
    const list = grouped.get(day)
    if (list) list.push(event)
    else grouped.set(day, [event])
  }
  return grouped
}

export function countByKind(events: CalendarEvent[]): Record<CalendarEventKind, number> {
  const counts: Record<CalendarEventKind, number> = {
    deadline: 0,
    class: 0,
    prac_app: 0,
    evaluation: 0,
    schedule: 0,
  }
  for (const event of events) counts[event.kind] += 1
  return counts
}

/** 24-hour military time: `13:30:00` becomes `1330`. */
export function formatTime(value: string | null): string | null {
  if (!value) return null
  const [hours, minutes] = value.split(':')
  return `${pad(Number(hours))}${pad(Number(minutes ?? 0))}`
}

export function formatTimeRange(start: string | null, end: string | null): string | null {
  const from = formatTime(start)
  const to = formatTime(end)
  if (from && to) return `${from}–${to}`
  return from ?? (to ? `Until ${to}` : null)
}

export function formatDateRange(start: Date, end: Date): string {
  const sameYear = start.getFullYear() === end.getFullYear()
  const startLabel = start.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  })
  const endLabel = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  return `${startLabel} – ${endLabel}`
}

export function formatWeekRange(weekStart: Date): string {
  return formatDateRange(weekStart, addDays(weekStart, 6))
}

export function formatDayHeading(date: Date): string {
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
}

export function weekdayShort(date: Date): string {
  return date.toLocaleDateString('en-US', { weekday: 'short' })
}

function icsEscape(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;')
}

function foldIcsLine(line: string): string {
  if (line.length <= 75) return line
  const parts = [line.slice(0, 75)]
  let rest = line.slice(75)
  while (rest.length > 0) {
    parts.push(` ${rest.slice(0, 74)}`)
    rest = rest.slice(74)
  }
  return parts.join('\r\n')
}

function compactDate(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, '')
}

function compactTime(value: string): string {
  const [hours, minutes, seconds] = value.split(':')
  return `${pad(Number(hours))}${pad(Number(minutes ?? 0))}${pad(Number(seconds ?? 0))}`
}

function shiftMinutes(isoDate: string, value: string, minutes: number): { date: string; time: string } {
  const [hours, mins, seconds] = value.split(':').map(Number)
  const total = (hours ?? 0) * 60 + (mins ?? 0) + minutes
  const dayShift = Math.floor(total / (24 * 60))
  const minutesInDay = ((total % (24 * 60)) + 24 * 60) % (24 * 60)
  return {
    date: toIsoDate(addDays(parseLocalDate(isoDate), dayShift)),
    time: `${pad(Math.floor(minutesInDay / 60))}${pad(minutesInDay % 60)}${pad(seconds ?? 0)}`,
  }
}

function icsInterval(event: CalendarEvent): { start: string; end: string } {
  const day = event.event_date.slice(0, 10)
  const dueAt = event.kind === 'deadline' ? (event.end_time ?? event.start_time) : null
  if (event.kind === 'deadline' && dueAt) {
    const end = { date: day, time: compactTime(dueAt) }
    const start = shiftMinutes(day, dueAt, -15)
    return { start: `${start.date.replace(/-/g, '')}T${start.time}`, end: `${compactDate(end.date)}T${end.time}` }
  }
  if (event.kind !== 'deadline' && event.start_time && event.end_time) {
    return {
      start: `${compactDate(day)}T${compactTime(event.start_time)}`,
      end: `${compactDate(day)}T${compactTime(event.end_time)}`,
    }
  }
  if (event.kind !== 'deadline' && event.start_time) {
    const end = shiftMinutes(day, event.start_time, 30)
    return {
      start: `${compactDate(day)}T${compactTime(event.start_time)}`,
      end: `${end.date.replace(/-/g, '')}T${end.time}`,
    }
  }
  const nextDay = compactDate(toIsoDate(addDays(parseLocalDate(day), 1)))
  return { start: `VALUE=DATE:${compactDate(day)}`, end: `VALUE=DATE:${nextDay}` }
}

/** UTC stamp `YYYYMMDDTHHMMSSZ` for a stable ICS file. */
export function icsStampFromDate(date: Date): string {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
}

function icsDescription(event: CalendarEvent): string | null {
  const identity = eventIdentity(event.title)
  const parts = [identity.id ? `ID: ${identity.id}` : null, event.notes].filter((part) => part)
  return parts.length > 0 ? parts.join('\n') : null
}

/** Same day, same clean title, and the same clock time count as one event. */
function dedupeCalendarEvents(events: CalendarEvent[]): CalendarEvent[] {
  const seen = new Set<string>()
  const unique: CalendarEvent[] = []
  for (const event of [...events].sort(compareEvents)) {
    const identity = eventIdentity(event.title)
    const key = [
      event.event_date.slice(0, 10),
      identity.title.trim().toLowerCase(),
      event.start_time ?? '',
      event.end_time ?? '',
    ].join('|')
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(event)
  }
  return unique
}

/** One calendar file for the events on screen. Times stay in local floating time. */
export function buildCalendarIcs(
  events: CalendarEvent[],
  options: { calendarName: string; stamp: string },
): string {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Arsenal//Calendar//EN',
    'CALSCALE:GREGORIAN',
    foldIcsLine(`X-WR-CALNAME:${icsEscape(options.calendarName)}`),
  ]
  for (const event of dedupeCalendarEvents(events)) {
    const identity = eventIdentity(event.title)
    const interval = icsInterval(event)
    const startLine = interval.start.startsWith('VALUE=DATE:')
      ? `DTSTART;${interval.start}`
      : `DTSTART:${interval.start}`
    const endLine = interval.end.startsWith('VALUE=DATE:')
      ? `DTEND;${interval.end}`
      : `DTEND:${interval.end}`
    const description = icsDescription(event)
    lines.push(
      'BEGIN:VEVENT',
      foldIcsLine(`UID:${icsEscape(event.id)}@arsenal`),
      `DTSTAMP:${options.stamp}`,
      foldIcsLine(`SUMMARY:${icsEscape(identity.title)}`),
      startLine,
      endLine,
    )
    if (event.location) lines.push(foldIcsLine(`LOCATION:${icsEscape(event.location)}`))
    if (description) lines.push(foldIcsLine(`DESCRIPTION:${icsEscape(description)}`))
    lines.push('END:VEVENT')
  }
  lines.push('END:VCALENDAR')
  return `${lines.join('\r\n')}\r\n`
}
