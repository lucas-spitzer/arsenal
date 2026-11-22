import { describe, expect, it } from 'vitest'
import {
  buildCalendarIcs,
  chipLabel,
  countByKind,
  eventIdentity,
  eventTimeLabel,
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
    completed_at: null,
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
    ).toEqual({ deadline: 2, class: 0, prac_app: 1, evaluation: 0, schedule: 0 })
  })
})

describe('eventIdentity', () => {
  it('splits a leading course code from the title', () => {
    expect(eventIdentity('B023029 End of day routine')).toEqual({
      id: 'B023029',
      title: 'End of day routine',
    })
    expect(eventIdentity('BS230009 Morning routine')).toEqual({
      id: 'BS230009',
      title: 'Morning routine',
    })
    expect(eventIdentity('B140310 Rifle range: ARQ day three, holds')).toEqual({
      id: 'B140310',
      title: 'Rifle range: ARQ day three, holds',
    })
    expect(eventIdentity('BSZ0009 Morning routine')).toEqual({
      id: 'BSZ0009',
      title: 'Morning routine',
    })
    expect(eventIdentity('B2A0380DM Tactical planning process guided application I')).toEqual({
      id: 'B2A0380DM',
      title: 'Tactical planning process guided application I',
    })
    expect(eventIdentity('B0Z9029 End of day routine')).toEqual({
      id: 'B0Z9029',
      title: 'End of day routine',
    })
    expect(eventIdentity('Hike to WTBN')).toEqual({ id: null, title: 'Hike to WTBN' })
    expect(eventIdentity('Flight Physicals')).toEqual({ id: null, title: 'Flight Physicals' })
  })
})

describe('deadline marks', () => {
  it('labels ODT, clocked, and EOD deadlines distinctly', () => {
    expect(chipLabel(event({ kind: 'deadline', title: 'Read Range Week SPINS' }))).toBe('Due ODT')
    expect(eventTimeLabel(event({ kind: 'deadline', title: 'Read Range Week SPINS' }))).toBe('Due ODT')
    expect(chipLabel(event({ kind: 'deadline', title: 'Read MCDP-1 Warfighting' }))).toBe('Due ODT')
    expect(eventTimeLabel(event({ kind: 'deadline', title: 'Read MCDP-1 Warfighting' }))).toBe('Due ODT')
    expect(eventTimeLabel(event({ kind: 'deadline', title: 'Acquire map gear' }))).toBe('Due EOD')
    expect(
      chipLabel(event({ kind: 'deadline', title: 'Contributions to Exam I Study Guide', start_time: '23:59:00' })),
    ).toBe('Due at 2359')
    expect(
      eventTimeLabel(event({ kind: 'deadline', title: 'Contributions to Exam I Study Guide', start_time: '23:59:00' })),
    ).toBe('Due at 2359')
  })

  it('orders ODT, then EOD, then clocked due times', () => {
    const grouped = groupEventsByDay([
      event({
        id: 'eod',
        title: 'Peer Evaluations & Self Reflection',
        kind: 'deadline',
        event_date: '2026-11-23',
      }),
      event({
        id: 'late',
        title: 'Asynchronous Assignments',
        kind: 'deadline',
        event_date: '2026-11-23',
        start_time: '23:59:00',
      }),
      event({
        id: 'odt',
        title: 'Read MCDP-1 Warfighting',
        kind: 'deadline',
        event_date: '2026-11-23',
      }),
      event({
        id: 'eod-z',
        title: 'Tactical task and tac planning shortcards',
        kind: 'deadline',
        event_date: '2026-11-23',
      }),
    ])

    expect(grouped.get('2026-11-23')?.map((item) => item.id)).toEqual(['odt', 'eod', 'eod-z', 'late'])
  })
})

describe('Friday hike order', () => {
  it('places the untimed hike after pistol qualification and before de-issue', () => {
    const grouped = groupEventsByDay([
      event({ id: 'deissue', title: 'Pistol de-issue', kind: 'schedule', event_date: '2026-11-20', start_time: '12:00:00', end_time: '18:00:00' }),
      event({ id: 'hike', title: 'Hike to McGlothlin Hall', kind: 'schedule', event_date: '2026-11-20' }),
      event({ id: 'range', title: 'B140310 Pistol range: blocks 4-5, pre-qualification and qualification', kind: 'evaluation', event_date: '2026-11-20', start_time: '08:00:00' }),
      event({ id: 'formation', title: 'B023029 Formation', kind: 'schedule', event_date: '2026-11-20', start_time: '18:10:00' }),
    ])

    expect(grouped.get('2026-11-20')?.map((item) => item.id)).toEqual(['range', 'hike', 'deissue', 'formation'])
    expect(eventTimeLabel(event({ title: 'Hike to McGlothlin Hall', kind: 'schedule' }))).toBeNull()
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

describe('buildCalendarIcs', () => {
  const stamp = '20261114T120000Z'

  it('keeps a timed block in local floating time', () => {
    const ics = buildCalendarIcs(
      [
        event({
          id: 'hike',
          kind: 'schedule',
          title: 'Hike to WTBN',
          event_date: '2026-11-16',
          start_time: '05:00:00',
          end_time: '05:45:00',
          location: 'Application Trail',
          notes: 'Bring the packing list, all of it.',
        }),
      ],
      { calendarName: 'Arsenal Nov 15 – Nov 21, 2026', stamp },
    )

    expect(ics).toContain('DTSTART:20261116T050000')
    expect(ics).toContain('DTEND:20261116T054500')
    expect(ics).toContain('SUMMARY:Hike to WTBN')
    expect(ics).toContain('DESCRIPTION:Bring the packing list\\, all of it.')
    expect(ics).not.toContain('DTSTART:20261116T050000Z')
  })

  it('writes a date-only deadline as an all-day event and a timed deadline as 15 minutes', () => {
    const ics = buildCalendarIcs(
      [
        event({
          id: 'spins',
          kind: 'deadline',
          title: 'Read Range Week SPINS',
          event_date: '2026-11-16',
        }),
        event({
          id: 'guide',
          kind: 'deadline',
          title: 'Contributions to Exam I Study Guide',
          event_date: '2026-11-23',
          start_time: '23:59:00',
        }),
      ],
      { calendarName: 'Arsenal', stamp },
    )

    expect(ics).toContain('DTSTART;VALUE=DATE:20261116')
    expect(ics).toContain('DTEND;VALUE=DATE:20261117')
    expect(ics).toContain('DTSTART:20261123T234400')
    expect(ics).toContain('DTEND:20261123T235900')
  })

  it('drops the course code from the title and skips a repeated block', () => {
    const ics = buildCalendarIcs(
      [
        event({
          id: 'routine-coded',
          kind: 'schedule',
          title: 'BS230009 Morning routine',
          event_date: '2026-11-16',
          start_time: '04:00:00',
          end_time: '04:30:00',
          notes: 'Accountability report is due to the XO.',
        }),
        event({
          id: 'routine-copy',
          kind: 'schedule',
          title: 'Morning routine',
          event_date: '2026-11-16',
          start_time: '04:00:00',
          end_time: '04:30:00',
        }),
        event({
          id: 'range',
          kind: 'prac_app',
          title: 'B140310 Rifle range: ARQ day three, holds',
          event_date: '2026-11-16',
          start_time: '06:00:00',
        }),
      ],
      { calendarName: 'Arsenal', stamp },
    )

    expect(ics).toContain('SUMMARY:Morning routine')
    expect(ics).not.toContain('SUMMARY:BS230009')
    expect(ics).toContain('SUMMARY:Rifle range: ARQ day three\\, holds')
    expect(ics).not.toContain('SUMMARY:B140310')
    expect(ics).toContain('DESCRIPTION:ID: BS230009\\nAccountability report is due to the XO.')
    expect(ics).toContain('DESCRIPTION:ID: B140310')
    expect(ics.match(/BEGIN:VEVENT/g)).toHaveLength(2)
  })
})

describe('formatWeekRange', () => {
  it('labels the Sunday through Saturday span', () => {
    expect(formatWeekRange(parseLocalDate('2026-10-25'))).toBe('Oct 25 – Oct 31, 2026')
    expect(formatWeekRange(parseLocalDate('2026-12-27'))).toBe('Dec 27, 2026 – Jan 2, 2027')
  })
})
