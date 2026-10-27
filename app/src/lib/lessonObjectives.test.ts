import { describe, expect, it } from 'vitest'
import {
  fileTypeLabel,
  filterLessons,
  formatFileSize,
  indexStatusLabel,
  lessonSeedPrompt,
  lessonStats,
  objectivesToText,
  parseObjectiveLines,
} from './lessonObjectives'
import type { Lesson, LessonObjective } from './lessonsApi'

function objective(overrides: Partial<LessonObjective>): LessonObjective {
  return {
    id: 'o1',
    lesson_id: 'l1',
    position: 1,
    text: 'Identify the steps of the OODA Cycle without omission.',
    code: 'MCS-CMBH-1002a',
    is_async: true,
    ...overrides,
  }
}

function lesson(overrides: Partial<Lesson>): Lesson {
  return {
    id: 'l1',
    workspace_id: 'ws-1',
    title: 'Decision Making',
    sort_order: 1,
    notes: null,
    created_by: null,
    created_at: '2026-10-27T00:00:00Z',
    updated_at: '2026-10-27T00:00:00Z',
    objectives: [objective({})],
    resources: [],
    ...overrides,
  }
}

describe('parseObjectiveLines', () => {
  it('reads numbered ELOs with async tags and trailing codes', () => {
    const parsed = parseObjectiveLines(`ENABLING LEARNING OBJECTIVES (ELOs):
1. Without the aid of references, identify the steps of the OODA Cycle without omission. [Async] (MCS-CMBH-1002a)

2. Given a mission and with the aid of references, utilize operation terms and graphics to communicate decisions with clarity. (MCS-LDR-1503a)`)

    expect(parsed).toEqual([
      {
        text: 'Without the aid of references, identify the steps of the OODA Cycle without omission.',
        code: 'MCS-CMBH-1002a',
        is_async: true,
      },
      {
        text: 'Given a mission and with the aid of references, utilize operation terms and graphics to communicate decisions with clarity.',
        code: 'MCS-LDR-1503a',
        is_async: false,
      },
    ])
  })

  it('keeps inline parentheses and joins wrapped lines', () => {
    const parsed = parseObjectiveLines(`12. Given an Individual First Aid Kit (IFAK) and references. Inventory an
Individual First Aid Kit (IFAK) To ensure it is complete. (MCS-MED-1001)`)

    expect(parsed).toHaveLength(1)
    expect(parsed[0].text).toBe(
      'Given an Individual First Aid Kit (IFAK) and references. Inventory an Individual First Aid Kit (IFAK) To ensure it is complete.',
    )
    expect(parsed[0].code).toBe('MCS-MED-1001')
  })

  it('treats each unnumbered line as its own ELO and allows missing codes', () => {
    expect(parseObjectiveLines('Define hazing.\nDefine fraternization. (MCS-VALU-1002g)')).toEqual([
      { text: 'Define hazing.', code: null, is_async: false },
      { text: 'Define fraternization.', code: 'MCS-VALU-1002g', is_async: false },
    ])
  })

  it('round-trips through objectivesToText', () => {
    const text = objectivesToText([objective({}), objective({ text: 'Define deadly force.', code: null, is_async: false })])
    expect(text).toBe(
      '1. Identify the steps of the OODA Cycle without omission. [Async] (MCS-CMBH-1002a)\n2. Define deadly force.',
    )
    expect(parseObjectiveLines(text)).toEqual([
      { text: 'Identify the steps of the OODA Cycle without omission.', code: 'MCS-CMBH-1002a', is_async: true },
      { text: 'Define deadly force.', code: null, is_async: false },
    ])
  })
})

describe('filterLessons', () => {
  const lessons = [
    lesson({}),
    lesson({
      id: 'l2',
      title: 'Standards of Conduct',
      objectives: [
        objective({ id: 'o2', lesson_id: 'l2', text: 'Define hazing without omission.', code: 'MCS-VALU-1002e' }),
        objective({ id: 'o3', lesson_id: 'l2', position: 2, text: 'Define fraternization.', code: 'MCS-VALU-1002g' }),
      ],
    }),
  ]

  it('returns everything for an empty query', () => {
    expect(filterLessons(lessons, '  ')).toHaveLength(2)
  })

  it('matches ELO text and codes, keeping only matching ELOs', () => {
    const byText = filterLessons(lessons, 'hazing')
    expect(byText.map((match) => match.lesson.id)).toEqual(['l2'])
    expect(byText[0].objectives.map((o) => o.id)).toEqual(['o2'])

    const byCode = filterLessons(lessons, 'mcs-valu')
    expect(byCode[0].objectives).toHaveLength(2)
  })

  it('shows every ELO when the class title matches', () => {
    const match = filterLessons(lessons, 'conduct')[0]
    expect(match.titleMatched).toBe(true)
    expect(match.objectives).toHaveLength(2)
  })
})

describe('display helpers', () => {
  it('counts classes, ELOs, and async ELOs', () => {
    expect(lessonStats([lesson({}), lesson({ objectives: [objective({ is_async: false })] })])).toEqual({
      classes: 2,
      elos: 2,
      async: 1,
    })
  })

  it('formats file sizes and types', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2 KB')
    expect(formatFileSize(3.5 * 1024 * 1024)).toBe('3.5 MB')
    expect(formatFileSize(null)).toBeNull()
    expect(fileTypeLabel({ kind: 'file', filename: 'OODA Loop.PPTX' })).toBe('PPTX')
    expect(fileTypeLabel({ kind: 'link', filename: null })).toBe('Link')
  })

  it('labels index status', () => {
    expect(indexStatusLabel({ kind: 'file', index_status: 'ready' })).toBe('Searchable')
    expect(indexStatusLabel({ kind: 'link', index_status: 'skipped' })).toBe('Not searchable (login required)')
  })

  it('lists ELOs in the discussion opener', () => {
    const prompt = lessonSeedPrompt(lesson({}))
    expect(prompt).toContain("Let's work through Decision Making.")
    expect(prompt).toContain('1. Identify the steps of the OODA Cycle without omission. (MCS-CMBH-1002a)')
    expect(lessonSeedPrompt(lesson({ objectives: [] }))).not.toContain('ELOs')
  })
})
