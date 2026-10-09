import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import { academyRailItems } from '../components/academy/types'
import { railItems } from '../components/foundry/types'
import { filterOutputs, wikiEntriesToOutputItems } from './academyOutputs'
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
    expect(values).not.toContain('wiki_knowledge')
    expect(values).not.toContain('flashcards')
  })

  it('omits wiki from Foundry and Academy rails', () => {
    expect(railItems.map((item) => item.id)).not.toContain('wiki')
    expect(academyRailItems.map((item) => item.id)).not.toContain('wiki')
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
})
