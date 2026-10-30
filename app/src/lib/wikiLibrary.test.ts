import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import { academyRailItems, academyPageForRole, academyRailForRole } from '../components/academy/types'
import { railItems } from '../components/foundry/types'
import {
  defaultReaderSourceId,
  filterOutputs,
  knowledgeRunOutputItems,
  libraryItemsForRole,
  outputFooter,
  wikiEntriesToOutputItems,
} from './academyOutputs'
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

  it('hides study materials, flashcards, questions, and scenarios from students and keeps them for admins', () => {
    expect(academyRailForRole(false).map((item) => item.id)).toEqual([
      'calendar',
      'library',
      'reader',
      'objectives',
      'discussions',
    ])
    expect(academyRailForRole(true).map((item) => item.id)).toEqual([
      'calendar',
      'library',
      'reader',
      'objectives',
      'discussions',
      'flashcards',
      'quiz',
      'scenarios',
    ])
    expect(academyPageForRole('flashcards', false)).toBe('library')
    expect(academyPageForRole('quiz', false)).toBe('library')
    expect(academyPageForRole('scenarios', false)).toBe('library')
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
    expect(libraryItemsForRole(items, false).map((item) => item.id)).toEqual(['book', 'wiki'])
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
    expect(outputFooter('flashcard', 'Armed Forces Officer', 'Chapter 1 Terms')).toBe('Chapter 1 Terms')
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
})

describe('knowledge run library cards', () => {
  const titles = new Map([
    ['run-1', 'Chapter 1'],
    ['run-2', 'Chapter 2'],
  ])

  function card(id: string, projectId: string, front: string) {
    return {
      id,
      source_id: 'src-1',
      knowledge_project_id: projectId,
      difficulty: 'medium',
      created_at: '2026-10-01T00:00:00Z',
      front,
      back: `${front} back`,
    }
  }

  it('groups each knowledge run into one flashcard, question, and scenario card', () => {
    const flashcards = knowledgeRunOutputItems(
      [card('c1', 'run-1', 'Commission'), card('c2', 'run-1', 'Valor'), card('c3', 'run-2', 'Tempo')],
      {
        kind: 'flashcard',
        runnerPage: 'flashcards',
        unit: 'card',
        plural: 'cards',
        titleOf: (record) => record.front,
        searchOf: (record) => `${record.front} ${record.back}`,
        nameOf: () => 'Armed Forces Officer',
        projectTitle: titles,
      },
    )
    const questions = knowledgeRunOutputItems(
      [
        {
          id: 'q1',
          source_id: 'src-1',
          knowledge_project_id: 'run-1',
          difficulty: 'easy',
          created_at: '2026-10-02T00:00:00Z',
          question: 'What is fidelity?',
        },
      ],
      {
        kind: 'question',
        runnerPage: 'quiz',
        unit: 'question',
        plural: 'questions',
        titleOf: (record) => record.question,
        searchOf: (record) => record.question,
        nameOf: () => 'Armed Forces Officer',
        projectTitle: titles,
      },
    )

    expect(flashcards.map((item) => item.id)).toEqual(['run-1', 'run-2'])
    expect(flashcards[0]).toMatchObject({
      kind: 'flashcard',
      title: '2 cards',
      footer: 'Chapter 1',
      sourceName: 'Armed Forces Officer',
      projectId: 'run-1',
      runnerPage: 'flashcards',
    })
    expect(flashcards[1]).toMatchObject({
      title: '1 card',
      footer: 'Chapter 2',
      projectId: 'run-2',
    })
    expect(questions[0]).toMatchObject({
      kind: 'question',
      title: '1 question',
      footer: 'Chapter 1',
      projectId: 'run-1',
    })
  })

  it('finds a run by one of its cards', () => {
    const items = knowledgeRunOutputItems([card('c1', 'run-1', 'Commission')], {
      kind: 'flashcard',
      runnerPage: 'flashcards',
      unit: 'card',
      plural: 'cards',
      titleOf: (record) => record.front,
      searchOf: (record) => `${record.front} ${record.back}`,
      nameOf: () => 'Armed Forces Officer',
      projectTitle: titles,
    })

    expect(filterOutputs(items, { search: 'Commission', type: 'all', sourceId: null })).toEqual(items)
    expect(filterOutputs(items, { search: 'missing', type: 'all', sourceId: null })).toEqual([])
  })
})
