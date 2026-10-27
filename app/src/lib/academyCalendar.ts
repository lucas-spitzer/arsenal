import type { LucideIcon } from 'lucide-react'
import { AlarmClock, ClipboardCheck, Compass, Presentation } from 'lucide-react'
import type { CalendarEvent, CalendarEventKind } from './calendarApi'

export type CalendarKindMeta = {
  label: string
  /** Short label for chips and the "Due" marker on deadlines. */
  chip: string
  icon: LucideIcon
  cls: string
}

export const calendarKinds: CalendarEventKind[] = ['class', 'prac_app', 'evaluation', 'deadline']

export const kindMeta: Record<CalendarEventKind, CalendarKindMeta> = {
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

export function compareEvents(a: CalendarEvent, b: CalendarEvent): number {
  if (a.event_date !== b.event_date) return a.event_date < b.event_date ? -1 : 1
  if (a.start_time !== b.start_time) {
    if (a.start_time == null) return -1
    if (b.start_time == null) return 1
    return a.start_time < b.start_time ? -1 : 1
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
  const counts: Record<CalendarEventKind, number> = { deadline: 0, class: 0, prac_app: 0, evaluation: 0 }
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
