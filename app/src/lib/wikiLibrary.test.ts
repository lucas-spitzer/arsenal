import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import { academyRailItems, academyPageForRole, academyRailForRole } from '../components/academy/types'
import { railItems } from '../components/foundry/types'
import {
  defaultReaderSourceId,
  filterOutputs,
  knowledgeLibraryItems,
  lessonLibraryItems,
  libraryItemsForRole,
  libraryShelves,
  outputFooter,
  type OutputItem,
  outputShelfKey,
  wikiElosToOutputItems,
  wikiEntriesToOutputItems,
} from './academyOutputs'
import type { Lesson } from './lessonsApi'
import { ARTIFACT_OPTIONS, type WikiEntry } from './workspaceApi'

function wikiEntry(overrides: Partial<WikiEntry> = {}): WikiEntry {
  return {
    id: 'wiki-1',
    workspace_id: 'ws-1',
    preferred_label: 'Enemy System',
    definition: 'Interdependent parts.',
    significance: null,
    category: null,
    items: [],
    entry_kind: 'term',
    importance: 'essential',
    status: 'canonical',
    canonical_slug: 'enemy-system',
    aliases: [],
    prerequisites: [],
    pronunciation: null,
    evidence: [{ source_id: 'src-evidence' }],
    origin: { source_id: 'src-origin' },
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
    ...overrides,
  }
}

describe('wiki knowledge on New Run and Library', () => {
  it('keeps document artifacts on New Run and leaves knowledge to Forge', () => {
    const values = ARTIFACT_OPTIONS.map((option) => option.value)
    expect(values).toContain('electronic_book')
    expect(values).toContain('wiki_json')
    expect(values).not.toContain('chapter_source')
    expect(values).not.toContain('wiki_knowledge')
    expect(values).not.toContain('flashcards')
  })

  it('omits wiki from Foundry and Academy rails', () => {
    expect(railItems.map((item) => item.id)).not.toContain('wiki')
    expect(academyRailItems.map((item) => item.id)).not.toContain('wiki')
  })

  it('omits calendar and elo from the Foundry rail', () => {
    const ids = railItems.map((item) => item.id)
    expect(ids).not.toContain('calendar')
    expect(ids).not.toContain('objectives')
  })

  it('hides study materials, flashcards, scenarios, and analytics from students and keeps quizzes visible', () => {
    expect(academyRailForRole(false).map((item) => item.id)).toEqual([
      'calendar',
      'library',
      'reader',
      'discussions',
    ])
    expect(academyRailForRole(true).map((item) => item.id)).toEqual([
      'leaderboard',
      'calendar',
      'library',
      'reader',
      'discussions',
      'flashcards',
      'quiz',
      'analytics',
    ])
    expect(academyRailItems.map((item) => item.id)).not.toContain('objectives')
    expect(academyRailItems.map((item) => item.id)).not.toContain('scenarios')
    expect(academyPageForRole('flashcards', false)).toBe('calendar')
    expect(academyPageForRole('quiz', false)).toBe('calendar')
    expect(academyPageForRole('analytics', false)).toBe('calendar')
    expect(academyPageForRole('scenarios', false)).toBe('calendar')
    expect(academyPageForRole('reader', false)).toBe('reader')
    expect(academyPageForRole('flashcards', true)).toBe('flashcards')

    const items = [
      { kind: 'book' as const, id: 'book' },
      { kind: 'material' as const, id: 'material' },
      { kind: 'flashcard' as const, id: 'cards' },
      { kind: 'question' as const, id: 'questions' },
      { kind: 'scenario' as const, id: 'scenarios' },
      { kind: 'wiki' as const, id: 'wiki' },
    ]
    expect(libraryItemsForRole(items, false).map((item) => item.id)).toEqual(['book', 'questions', 'wiki'])
    expect(libraryItemsForRole(items, true).map((item) => item.id)).toEqual([
      'book',
      'material',
      'cards',
      'questions',
      'scenarios',
      'wiki',
    ])
  })

  it('maps each source’s canonical wiki entries into one Library card', () => {
    const items = wikiEntriesToOutputItems(
      [
        wikiEntry(),
        wikiEntry({
          id: 'wiki-2',
          preferred_label: 'Retired',
          status: 'deprecated',
        }),
        wikiEntry({
          id: 'wiki-3',
          preferred_label: 'Tempo',
          origin: {},
          evidence: [{ source_id: 'src-evidence' }],
        }),
      ],
      (id) => (id === 'src-origin' ? 'OCS Prep' : id === 'src-evidence' ? 'Evidence Book' : 'Unassigned'),
    )

    expect(items.map((item) => item.id)).toEqual(['src-origin', 'src-evidence'])
    expect(items[0]).toMatchObject({
      kind: 'wiki',
      title: '1 entry',
      sourceId: 'src-origin',
      sourceName: 'OCS Prep',
      runnerPage: 'wiki',
      searchText: 'Enemy System',
    })
    expect(items[1]).toMatchObject({
      id: 'src-evidence',
      title: '1 entry',
      sourceId: 'src-evidence',
      sourceName: 'Evidence Book',
      runnerPage: 'wiki',
      searchText: 'Tempo',
    })
  })

  it('counts every canonical term on the same source', () => {
    const items = wikiEntriesToOutputItems(
      [
        wikiEntry(),
        wikiEntry({
          id: 'wiki-4',
          preferred_label: 'Friction',
          created_at: '2026-09-15T00:00:00Z',
        }),
        wikiEntry({
          id: 'wiki-2',
          preferred_label: 'Retired',
          status: 'deprecated',
        }),
        wikiEntry({
          id: 'wiki-elo',
          preferred_label: 'Explain the commission.',
          entry_kind: 'elo',
          definition: 'A commission is a grant of authority.',
        }),
      ],
      () => 'OCS Prep',
    )

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      id: 'src-origin',
      title: '2 entries',
      createdAt: '2026-09-15T00:00:00Z',
      searchText: 'Enemy System Friction',
    })
  })

  it('finds a source wiki card by term label', () => {
    const items = wikiEntriesToOutputItems(
      [wikiEntry({ preferred_label: 'War' })],
      () => 'MCDP 1 Warfighting',
    )

    expect(filterOutputs(items, { search: 'War', type: 'all', sourceId: null })).toEqual(items)
    expect(filterOutputs(items, { search: 'missing', type: 'all', sourceId: null })).toEqual([])
  })

  it('puts the book title on a wiki card and keeps every entry for that source together', () => {
    const items = wikiEntriesToOutputItems(
      [
        wikiEntry(),
        wikiEntry({
          id: 'wiki-4',
          preferred_label: 'Friction',
          created_at: '2026-09-16T00:00:00Z',
        }),
      ],
      () => 'Armed Forces Officer',
    )

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      footer: 'Armed Forces Officer',
      sourceName: 'Armed Forces Officer',
      title: '2 entries',
      projectId: null,
    })
    expect(outputFooter('book', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Armed Forces Officer')
    expect(outputFooter('audio', 'Armed Forces Officer', null)).toBe('Armed Forces Officer')
    expect(outputFooter('wiki', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Armed Forces Officer')
    expect(outputFooter('material', 'Study Material', 'Oath Cutout')).toBe('Oath Cutout')
    expect(outputFooter('flashcard', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Armed Forces Officer')
    expect(outputFooter('question', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Armed Forces Officer')
    expect(outputFooter('scenario', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Armed Forces Officer')
  })
})

function lesson(overrides: Partial<Lesson> = {}): Lesson {
  return {
    id: 'lesson-1',
    workspace_id: 'ws-1',
    title: 'Combat Orders',
    sort_order: 0,
    notes: null,
    created_by: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    objectives: [
      {
        id: 'obj-1',
        lesson_id: 'lesson-1',
        position: 1,
        text: 'Identify the steps of the OODA Cycle.',
        code: 'MCS-CMBH-1002a',
        is_async: false,
      },
    ],
    resources: [],
    ...overrides,
  }
}

describe('library ELO shelves', () => {
  it('puts one ELO item on a class shelf and keeps an empty class out', () => {
    const items = lessonLibraryItems([
      lesson({
        objectives: [
          {
            id: 'obj-1',
            lesson_id: 'lesson-1',
            position: 1,
            text: 'Identify the steps of the OODA Cycle.',
            code: 'MCS-CMBH-1002a',
            is_async: false,
          },
          {
            id: 'obj-2',
            lesson_id: 'lesson-1',
            position: 2,
            text: 'Communicate a decision with operation terms.',
            code: null,
            is_async: true,
          },
        ],
      }),
      lesson({ id: 'lesson-empty', title: 'Empty Class', objectives: [], resources: [] }),
    ])

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'elo',
      id: 'lesson-1',
      title: '2 ELOs',
      sourceId: null,
      lessonId: 'lesson-1',
      sourceName: 'Combat Orders',
      runnerPage: 'objectives',
    })
    expect(items[0]?.searchText).toContain('OODA Cycle')
    expect(items[0]?.searchText).toContain('MCS-CMBH-1002a')
  })

  it('keeps a class that only has materials', () => {
    const items = lessonLibraryItems([
      lesson({
        id: 'lesson-files',
        title: 'Land Navigation',
        objectives: [],
        resources: [
          {
            id: 'res-1',
            lesson_id: 'lesson-files',
            kind: 'file',
            label: 'Slides',
            position: 0,
            url: null,
            filename: 'slides.pdf',
            mime_type: 'application/pdf',
            file_size_bytes: 10,
            index_status: 'ready',
            index_error: null,
            created_at: '2026-09-01T00:00:00Z',
            updated_at: '2026-09-04T00:00:00Z',
          },
        ],
      }),
    ])

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'elo',
      lessonId: 'lesson-files',
      title: '1 material',
      sourceName: 'Land Navigation',
      createdAt: '2026-09-04T00:00:00Z',
    })
    expect(items[0]?.searchText).toContain('Slides')
  })

  it('puts knowledge ELOs on their source and leaves them off the wiki card', () => {
    const entries = [
      wikiEntry({ preferred_label: 'Enemy System' }),
      wikiEntry({
        id: 'wiki-elo',
        preferred_label: 'Explain the commission.',
        entry_kind: 'elo',
      }),
      wikiEntry({
        id: 'wiki-elo-2',
        preferred_label: 'State the oath.',
        entry_kind: 'elo',
        created_at: '2026-09-20T00:00:00Z',
      }),
      wikiEntry({
        id: 'wiki-retired-elo',
        preferred_label: 'Retired objective.',
        entry_kind: 'elo',
        status: 'deprecated',
      }),
    ]
    const nameOf = () => 'OCS Prep'

    expect(wikiEntriesToOutputItems(entries, nameOf)).toHaveLength(1)
    expect(wikiEntriesToOutputItems(entries, nameOf)[0]).toMatchObject({ kind: 'wiki', title: '1 entry' })
    const elos = wikiElosToOutputItems(entries, nameOf)
    expect(elos).toHaveLength(1)
    expect(elos[0]).toMatchObject({
      kind: 'elo',
      id: 'src-origin',
      title: '2 ELOs',
      sourceId: 'src-origin',
      lessonId: null,
      sourceName: 'OCS Prep',
      runnerPage: 'wiki',
      createdAt: '2026-09-20T00:00:00Z',
    })
    expect(elos[0]?.searchText).toContain('Explain the commission.')
  })

  it('keeps a class shelf separate from a book shelf with the same name', () => {
    const classItem = lessonLibraryItems([lesson({ title: 'Warfighting' })])[0]
    const bookItem = wikiElosToOutputItems(
      [wikiEntry({ preferred_label: 'Explain tempo.', entry_kind: 'elo', origin: { source_id: 'src-book' }, evidence: [] })],
      () => 'Warfighting',
    )[0]
    expect(classItem && bookItem).toBeTruthy()
    if (!classItem || !bookItem) return
    expect(outputShelfKey(classItem)).toBe('lesson:lesson-1')
    expect(outputShelfKey(bookItem)).toBe('source:src-book')
    expect(filterOutputs([classItem, bookItem], { search: '', type: 'all', sourceId: 'lesson-1' })).toEqual([classItem])
    expect(filterOutputs([classItem, bookItem], { search: '', type: 'elo', sourceId: 'src-book' })).toEqual([bookItem])
  })
})

describe('reader default book', () => {
  const books = [
    { sourceId: 'src-z', sourceName: 'Zebra Manual', createdAt: '2026-01-01T00:00:00Z' },
    { sourceId: 'src-afo', sourceName: 'Armed Forces Officer', createdAt: '2026-06-01T00:00:00Z' },
  ]

  it('opens the favorited book', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: 'src-z',
        books,
      }),
    ).toBe('src-z')
  })

  it('opens the first book when nothing is favorited', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: null,
        books,
      }),
    ).toBe('src-afo')
  })

  it('keeps a direct reader link', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: 'src-link',
        focusedSourceId: 'src-z',
        books,
      }),
    ).toBe('src-link')
  })

  it('falls through when the favorite is no longer a book', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: 'gone',
        books,
      }),
    ).toBe('src-afo')
  })

  it('opens MCDP 1 Warfighting for The Basic School when nothing is chosen', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: null,
        workspaceName: 'The Basic School',
        books: [
          ...books,
          { sourceId: 'src-mcdp', sourceName: 'MCDP 1 Warfighting', createdAt: '2026-03-01T00:00:00Z' },
        ],
      }),
    ).toBe('src-mcdp')
  })

  it('recognizes the Warfighting filename as that same default book', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: null,
        workspaceName: 'The Basic School',
        books: [
          ...books,
          { sourceId: 'src-wf', sourceName: 'Warfighting.pdf', createdAt: '2026-03-01T00:00:00Z' },
        ],
      }),
    ).toBe('src-wf')
  })

  it('keeps a favorite ahead of the platoon default', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: 'src-afo',
        workspaceName: 'The Basic School',
        books: [
          ...books,
          { sourceId: 'src-mcdp', sourceName: 'MCDP 1 Warfighting', createdAt: '2026-03-01T00:00:00Z' },
        ],
      }),
    ).toBe('src-afo')
  })

  it('keeps alphabetical order in another workspace', () => {
    expect(
      defaultReaderSourceId({
        routeSourceId: null,
        focusedSourceId: null,
        workspaceName: 'Another Platoon',
        books: [
          ...books,
          { sourceId: 'src-mcdp', sourceName: 'MCDP 1 Warfighting', createdAt: '2026-03-01T00:00:00Z' },
        ],
      }),
    ).toBe('src-afo')
  })
})

describe('knowledge library cards', () => {
  function card(id: string, sourceId: string, front: string, createdAt = '2026-10-01T00:00:00Z') {
    return {
      id,
      source_id: sourceId,
      difficulty: 'medium',
      created_at: createdAt,
      front,
      back: `${front} back`,
    }
  }

  it('rolls every batch for a source into one card with the quantity', () => {
    const flashcards = knowledgeLibraryItems(
      [
        card('c1', 'src-1', 'Commission'),
        card('c2', 'src-1', 'Valor', '2026-10-03T00:00:00Z'),
        card('c3', 'src-2', 'Tempo'),
      ],
      {
        kind: 'flashcard',
        runnerPage: 'flashcards',
        unit: 'card',
        plural: 'cards',
        searchOf: (record) => `${record.front} ${record.back}`,
        nameOf: (id) => (id === 'src-2' ? 'MCDP 1' : 'Armed Forces Officer'),
      },
    )
    const questions = knowledgeLibraryItems(
      [
        {
          id: 'q1',
          source_id: 'src-1',
          difficulty: 'easy',
          created_at: '2026-10-02T00:00:00Z',
          question: 'What is fidelity?',
        },
        {
          id: 'q2',
          source_id: 'src-1',
          difficulty: 'hard',
          created_at: '2026-10-04T00:00:00Z',
          question: 'What is friction?',
        },
      ],
      {
        kind: 'question',
        runnerPage: 'quiz',
        unit: 'question',
        plural: 'questions',
        searchOf: (record) => record.question,
        nameOf: () => 'Armed Forces Officer',
      },
    )

    expect(flashcards.map((item) => item.id)).toEqual(['src-1', 'src-2'])
    expect(flashcards[0]).toMatchObject({
      kind: 'flashcard',
      title: '2 cards',
      footer: 'Armed Forces Officer',
      sourceName: 'Armed Forces Officer',
      projectId: null,
      runnerPage: 'flashcards',
      createdAt: '2026-10-03T00:00:00Z',
    })
    expect(flashcards[1]).toMatchObject({
      title: '1 card',
      footer: 'MCDP 1',
      projectId: null,
    })
    expect(questions[0]).toMatchObject({
      kind: 'question',
      title: '2 questions',
      footer: 'Armed Forces Officer',
      projectId: null,
    })
  })

  it('finds a source card by one of its cards', () => {
    const items = knowledgeLibraryItems([card('c1', 'src-1', 'Commission')], {
      kind: 'flashcard',
      runnerPage: 'flashcards',
      unit: 'card',
      plural: 'cards',
      searchOf: (record) => `${record.front} ${record.back}`,
      nameOf: () => 'Armed Forces Officer',
    })

    expect(filterOutputs(items, { search: 'Commission', type: 'all', sourceId: null })).toEqual(items)
    expect(filterOutputs(items, { search: 'missing', type: 'all', sourceId: null })).toEqual([])
  })
})

function shelfItem(
  overrides: Partial<OutputItem> & Pick<OutputItem, 'kind' | 'id' | 'sourceName'>,
): OutputItem {
  return {
    title: overrides.kind,
    sourceId: overrides.lessonId ? null : 'src-1',
    lessonId: null,
    footer: overrides.sourceName,
    badge: '',
    createdAt: '2026-10-01T00:00:00Z',
    runnerPage: null,
    isAudio: false,
    isEbook: false,
    isNarration: false,
    isAudiobook: false,
    narrationDownload: null,
    projectId: null,
    ...overrides,
  }
}

describe('library shelves', () => {
  const items = [
    shelfItem({ kind: 'book', id: 'book', sourceName: 'Armed Forces Officer', createdAt: '2026-11-15T00:00:00Z' }),
    shelfItem({ kind: 'wiki', id: 'wiki', sourceName: 'Armed Forces Officer', createdAt: '2026-11-01T00:00:00Z' }),
    shelfItem({ kind: 'question', id: 'questions', sourceName: 'Armed Forces Officer', createdAt: '2026-10-01T00:00:00Z' }),
    shelfItem({
      kind: 'elo',
      id: 'virtues',
      sourceName: 'Cardinal Virtues',
      sourceId: null,
      lessonId: 'lesson-virtues',
      createdAt: '2026-10-29T18:00:00Z',
    }),
    shelfItem({
      kind: 'elo',
      id: 'decision',
      sourceName: 'Decision Making',
      sourceId: null,
      lessonId: 'lesson-decision',
      createdAt: '2026-10-27T00:00:00Z',
    }),
    shelfItem({
      kind: 'elo',
      id: 'human',
      sourceName: 'Human Performance Methodologies',
      sourceId: null,
      lessonId: 'lesson-human',
      createdAt: '2026-10-29T01:00:00Z',
    }),
    shelfItem({
      kind: 'elo',
      id: 'uniforms',
      sourceName: 'Marine Corps Uniforms and Customs and Courtesies',
      sourceId: null,
      lessonId: 'lesson-uniforms',
      createdAt: '',
    }),
  ]

  it('puts book shelves above class shelves and keeps other book tiles under All', () => {
    const shelves = libraryShelves(items)

    expect(shelves.books.map((shelf) => shelf.name)).toEqual(['Armed Forces Officer'])
    expect(shelves.books[0]?.items.map((item) => item.kind)).toEqual(['book', 'wiki', 'question'])
    expect(shelves.classes.map((shelf) => shelf.name)).toEqual([
      'Cardinal Virtues',
      'Decision Making',
      'Human Performance Methodologies',
      'Marine Corps Uniforms and Customs and Courtesies',
    ])
  })

  it('filters book tiles without changing class shelves', () => {
    const shelves = libraryShelves(items, { bookKind: 'wiki', classKind: 'elo' })

    expect(shelves.books[0]?.items.map((item) => item.kind)).toEqual(['wiki'])
    expect(shelves.classes).toHaveLength(4)
  })

  it('puts practice questions on the class shelf and keeps them under Quiz', () => {
    const questions = knowledgeLibraryItems(
      [{
        id: 'q1',
        lesson_id: 'lesson-virtues',
        source_id: null,
        difficulty: 'easy',
        created_at: '2026-10-02T00:00:00Z',
        question: 'What does MEF stand for?',
      }],
      {
        kind: 'question',
        runnerPage: 'quiz',
        unit: 'question',
        plural: 'questions',
        searchOf: (record) => record.question,
        nameOf: () => 'Cardinal Virtues',
      },
    )

    expect(questions[0]).toMatchObject({
      lessonId: 'lesson-virtues',
      sourceId: null,
      sourceName: 'Cardinal Virtues',
      title: '1 question',
    })
    const shelves = libraryShelves(
      [
        ...questions,
        shelfItem({
          kind: 'elo',
          id: 'virtues',
          sourceName: 'Cardinal Virtues',
          sourceId: null,
          lessonId: 'lesson-virtues',
        }),
      ],
      { classKind: 'quiz' },
    )
    expect(shelves.classes[0]?.items.map((item) => item.kind)).toEqual(['question'])
    expect(shelves.books).toEqual([])
  })

  it('drops a shelf whose tiles are filtered out and leaves classes empty for Quiz', () => {
    const wikiOnly = libraryShelves(items, { bookKind: 'audio' })
    const quizzes = libraryShelves(items, { classKind: 'quiz' })

    expect(wikiOnly.books).toEqual([])
    expect(wikiOnly.classes).toHaveLength(4)
    expect(quizzes.classes).toEqual([])
    expect(quizzes.books).toHaveLength(1)
  })

  it('sorts each section by name, and by day with an undated shelf last', () => {
    const byName = libraryShelves(items, { sort: 'name' })
    const byUpdated = libraryShelves(items, { sort: 'updated' })

    expect(byName.classes.map((shelf) => shelf.name)).toEqual([
      'Cardinal Virtues',
      'Decision Making',
      'Human Performance Methodologies',
      'Marine Corps Uniforms and Customs and Courtesies',
    ])
    expect(byUpdated.classes.map((shelf) => shelf.name)).toEqual([
      'Cardinal Virtues',
      'Human Performance Methodologies',
      'Decision Making',
      'Marine Corps Uniforms and Customs and Courtesies',
    ])
  })
})
