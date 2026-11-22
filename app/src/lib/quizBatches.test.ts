import { describe, expect, it } from 'vitest'
import { defaultQuizBatch, listQuizBatches, quizBatchKey } from './quizBatches'

const titles = [
  { id: 'proj-old', title: 'Chapter 1' },
  { id: 'proj-new', title: 'Chapter 2' },
]

const quizzes = [
  { source_id: 'src-a', knowledge_project_id: 'proj-old', created_at: '2026-10-01T00:00:00Z' },
  { source_id: 'src-a', knowledge_project_id: 'proj-new', created_at: '2026-10-20T00:00:00Z' },
  { source_id: 'src-a', knowledge_project_id: null, created_at: '2026-10-21T00:00:00Z' },
  { source_id: null, knowledge_project_id: null, created_at: '2026-09-01T00:00:00Z' },
]

function nameOf(sourceId: string | null): string {
  if (sourceId === 'src-a') return 'AFO'
  return 'Unassigned'
}

describe('listQuizBatches', () => {
  it('groups questions into knowledge batches and an unassigned batch per source', () => {
    const batches = listQuizBatches(quizzes, titles, nameOf)
    expect(batches.map((batch) => [batch.sourceName, batch.title])).toEqual([
      ['AFO', 'Unassigned'],
      ['AFO', 'Chapter 2'],
      ['AFO', 'Chapter 1'],
      ['Unassigned', 'Unassigned'],
    ])
    expect(batches[1]).toMatchObject({ sourceName: 'AFO', questionCount: 1, projectId: 'proj-new' })
    expect(batches[0]).toMatchObject({ key: quizBatchKey('src-a', null), sourceName: 'AFO' })
    expect(batches[3]?.sourceName).toBe('Unassigned')
  })

  it('hides wiki-term questions from Quiz batches', () => {
    const batches = listQuizBatches(
      [
        ...quizzes,
        {
          source_id: 'src-a',
          knowledge_project_id: 'proj-term',
          created_at: '2026-10-22T00:00:00Z',
          origin: { source: 'wiki_term' },
        },
      ],
      [...titles, { id: 'proj-term', title: 'Term practice' }],
      nameOf,
    )
    expect(batches.some((batch) => batch.projectId === 'proj-term')).toBe(false)
  })
})

describe('defaultQuizBatch', () => {
  const batches = listQuizBatches(quizzes, titles, nameOf)

  it('opens the newest batch when nothing is selected', () => {
    expect(defaultQuizBatch(batches, {})?.projectId).toBe('proj-new')
  })

  it('opens the newest named batch in a source from the library', () => {
    expect(defaultQuizBatch(batches, { sourceId: 'src-a' })?.title).toBe('Chapter 2')
  })

  it('opens a named batch, including one with no knowledge project', () => {
    expect(defaultQuizBatch(batches, { projectId: 'proj-old' })?.title).toBe('Chapter 1')
    expect(defaultQuizBatch(batches, { batchKey: quizBatchKey('src-a', null) })?.title).toBe('Unassigned')
  })
})
