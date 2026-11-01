import { describe, expect, it } from 'vitest'
import { discussionSections, discussionSourceGroups } from './discussionPrompts'
import type { WikiEntry } from './workspaceApi'

function entry(overrides: Partial<WikiEntry>): WikiEntry {
  return {
    id: 'wiki-1',
    workspace_id: 'ws-1',
    preferred_label: 'Explain the commission.',
    definition: 'A commission is a grant of authority.',
    significance: null,
    category: null,
    items: [],
    entry_kind: 'elo',
    importance: 'supporting',
    status: 'canonical',
    canonical_slug: 'explain-the-commission',
    aliases: [],
    prerequisites: [],
    pronunciation: null,
    evidence: [{ source_id: 'book-1' }],
    origin: {
      knowledge_project_id: 'project-1',
      section_title: 'Chapter 1 - Armed Forces Officer',
      elo_index: 0,
    },
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...overrides,
  }
}

describe('discussionSections', () => {
  it('groups each upload under its title and keeps file order', () => {
    const sections = discussionSections([
      entry({
        id: 'oath',
        preferred_label: 'Explain the oath.',
        origin: {
          knowledge_project_id: 'project-1',
          section_title: 'Chapter 1 - Armed Forces Officer',
          elo_index: 1,
        },
        created_at: '2026-10-01T00:00:02Z',
      }),
      entry({
        id: 'war',
        preferred_label: 'Explain friction.',
        evidence: [{ source_id: 'book-2' }],
        origin: {
          knowledge_project_id: 'project-2',
          section_title: 'Chapter 1 - Warfighting',
          elo_index: 0,
        },
        created_at: '2026-10-02T00:00:00Z',
      }),
      entry({
        id: 'term',
        entry_kind: 'term',
        preferred_label: 'Friction',
      }),
      entry({
        id: 'retired',
        preferred_label: 'Explain a retired objective.',
        status: 'deprecated',
      }),
      entry({
        id: 'commission',
        preferred_label: 'Explain the commission.',
        origin: {
          knowledge_project_id: 'project-1',
          section_title: 'Chapter 1 - Armed Forces Officer',
          elo_index: 0,
        },
        created_at: '2026-10-01T00:00:01Z',
      }),
    ])

    expect(sections.map((section) => section.title)).toEqual([
      'Chapter 1 - Armed Forces Officer',
      'Chapter 1 - Warfighting',
    ])
    expect(sections[0].prompts.map((prompt) => prompt.title)).toEqual([
      'Explain the commission.',
      'Explain the oath.',
    ])
    expect(sections[0].prompts[0].sourceId).toBe('book-1')
    expect(sections.map((section) => section.sourceId)).toEqual(['book-1', 'book-2'])
    expect(sections[1].prompts.map((prompt) => prompt.prompt)).toEqual(['Explain friction.'])
  })
})

describe('discussionSourceGroups', () => {
  const sections = discussionSections([
    entry({
      id: 'afo-2',
      origin: { knowledge_project_id: 'afo-ch2', section_title: 'Chapter 2', elo_index: 0 },
      created_at: '2026-10-03T00:00:00Z',
    }),
    entry({
      id: 'war-1',
      evidence: [{ source_id: 'book-2' }],
      origin: { knowledge_project_id: 'war-ch1', section_title: 'Chapter 1', elo_index: 0 },
      created_at: '2026-10-02T00:00:00Z',
    }),
    entry({
      id: 'afo-1',
      origin: { knowledge_project_id: 'afo-ch1', section_title: 'Chapter 1', elo_index: 0 },
      created_at: '2026-10-01T00:00:00Z',
    }),
    entry({
      id: 'orphan',
      evidence: [],
      origin: { knowledge_project_id: 'orphan-batch', section_title: 'Loose notes', elo_index: 0 },
      created_at: '2026-10-04T00:00:00Z',
    }),
    entry({
      id: 'deleted-source',
      evidence: [{ source_id: 'book-gone' }],
      origin: { knowledge_project_id: 'gone-batch', section_title: 'Old notes', elo_index: 0 },
      created_at: '2026-10-05T00:00:00Z',
    }),
  ])
  const sources = [
    { id: 'book-2', name: 'Warfighting' },
    { id: 'book-1', name: 'AFO' },
  ]

  it('groups batches under their source, sorted by name, oldest batch first', () => {
    const groups = discussionSourceGroups(sections, sources)

    expect(groups.map((group) => group.name)).toEqual(['AFO', 'Warfighting', 'Unassigned'])
    expect(groups[0].sourceId).toBe('book-1')
    expect(groups[0].sections.map((section) => section.title)).toEqual(['Chapter 1', 'Chapter 2'])
    expect(groups[1].sections.map((section) => section.key)).toEqual(['war-ch1'])
  })

  it('puts batches without a known source under Unassigned', () => {
    const groups = discussionSourceGroups(sections, sources)
    const unassigned = groups[groups.length - 1]

    expect(unassigned.sourceId).toBeNull()
    expect(unassigned.sections.map((section) => section.key)).toEqual(['orphan-batch', 'gone-batch'])
  })
})