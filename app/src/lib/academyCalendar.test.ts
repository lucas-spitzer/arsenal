import { describe, expect, it } from 'vitest'
import {
  countByKind,
  formatTime,
  formatTimeRange,
  formatWeekRange,
  groupEventsByDay,
  parseLocalDate,
  startOfWeek,
  toIsoDate,
  weekDays,
} from './academyCalendar'
import type { CalendarEvent } from './calendarApi'

function event(overrides: Partial<CalendarEvent>): CalendarEvent {
  return {
    id: 'ev-1',
    workspace_id: 'ws-1',
    title: 'TCCC Class',
    kind: 'class',
    event_date: '2026-10-26',
    start_time: null,
    end_time: null,
    location: 'CR-3',
    notes: null,
    created_by: null,
    created_at: '2026-10-20T00:00:00Z',
    updated_at: '2026-10-20T00:00:00Z',
    ...overrides,
  }
}

describe('parseLocalDate', () => {
  it('keeps the calendar day regardless of time zone', () => {
    const date = parseLocalDate('2026-10-25')
    expect(date.getFullYear()).toBe(2026)
    expect(date.getMonth()).toBe(9)
    expect(date.getDate()).toBe(25)
    expect(toIsoDate(date)).toBe('2026-10-25')
  })
})

describe('startOfWeek', () => {
  it('starts the week on Sunday', () => {
    expect(toIsoDate(startOfWeek(parseLocalDate('2026-10-27')))).toBe('2026-10-25')
    expect(toIsoDate(startOfWeek(parseLocalDate('2026-10-25')))).toBe('2026-10-25')
    expect(toIsoDate(startOfWeek(parseLocalDate('2026-10-31')))).toBe('2026-10-25')
  })

  it('crosses month and year boundaries', () => {
    expect(toIsoDate(startOfWeek(parseLocalDate('2027-01-01')))).toBe('2026-12-27')
  })
})

describe('weekDays', () => {
  it('returns seven consecutive days', () => {
    const days = weekDays(parseLocalDate('2026-10-25')).map(toIsoDate)
    expect(days).toEqual([
      '2026-10-25',
      '2026-10-26',
      '2026-10-27',
      '2026-10-28',
      '2026-10-29',
      '2026-10-30',
      '2026-10-31',
    ])
  })
})

describe('groupEventsByDay', () => {
  it('groups by date and sorts untimed items first, then by time and title', () => {
    const grouped = groupEventsByDay([
      event({ id: 'c', title: 'Intro to Marine Corps History', event_date: '2026-10-30', start_time: '13:00:00' }),
      event({ id: 'a', title: 'Field and Garrison Diet', event_date: '2026-10-30', start_time: '08:00:00' }),
      event({ id: 'q', title: 'Complete TCCC Quiz', kind: 'deadline', event_date: '2026-10-25' }),
      event({ id: 'b', title: 'Intro to Anatomy and Biomechanics', event_date: '2026-10-30' }),
    ])

    expect([...grouped.keys()]).toEqual(['2026-10-25', '2026-10-30'])
    expect(grouped.get('2026-10-30')?.map((item) => item.id)).toEqual(['b', 'a', 'c'])
  })
})

describe('countByKind', () => {
  it('counts each kind', () => {
    expect(
      countByKind([event({ kind: 'deadline' }), event({ kind: 'deadline' }), event({ kind: 'prac_app' })]),
    ).toEqual({ deadline: 2, class: 0, prac_app: 1, evaluation: 0 })
  })
})

describe('time formatting', () => {
  it('uses 24-hour military time', () => {
    expect(formatTime('08:00:00')).toBe('0800')
    expect(formatTime('13:30:00')).toBe('1330')
    expect(formatTime(null)).toBeNull()
    expect(formatTimeRange('08:00:00', '11:30:00')).toBe('0800–1130')
    expect(formatTimeRange('08:00:00', null)).toBe('0800')
    expect(formatTimeRange(null, null)).toBeNull()
  })
})

describe('formatWeekRange', () => {
  it('labels the Sunday through Saturday span', () => {
    expect(formatWeekRange(parseLocalDate('2026-10-25'))).toBe('Oct 25 – Oct 31, 2026')
    expect(formatWeekRange(parseLocalDate('2026-12-27'))).toBe('Dec 27, 2026 – Jan 2, 2027')
  })
})
