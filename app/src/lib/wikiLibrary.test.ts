import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import { academyRailItems } from '../components/academy/types'
import { railItems } from '../components/foundry/types'
import { wikiEntriesToOutputItems } from './academyOutputs'
import { ARTIFACT_OPTIONS, type WikiEntry } from './workspaceApi'

function wikiEntry(overrides: Partial<WikiEntry> = {}): WikiEntry {
  return {
    id: 'wiki-1',
    workspace_id: 'ws-1',
    preferred_label: 'Enemy System',
    definition: 'Interdependent parts.',
    entry_kind: 'concept',
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
  it('lists Wiki Knowledge as a New Run artifact', () => {
    expect(ARTIFACT_OPTIONS.map((option) => option.value)).toContain('wiki_knowledge')
    expect(ARTIFACT_OPTIONS.find((option) => option.value === 'wiki_knowledge')?.label).toBe(
      'Wiki Knowledge',
    )
  })

  it('omits wiki from Foundry and Academy rails', () => {
    expect(railItems.map((item) => item.id)).not.toContain('wiki')
    expect(academyRailItems.map((item) => item.id)).not.toContain('wiki')
  })

  it('maps canonical wiki entries into Library outputs', () => {
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

    expect(items.map((item) => item.id)).toEqual(['wiki-1', 'wiki-3'])
    expect(items[0]).toMatchObject({
      kind: 'wiki',
      title: 'Enemy System',
      badge: 'concept',
      sourceId: 'src-origin',
      sourceName: 'OCS Prep',
      runnerPage: 'wiki',
    })
    expect(items[1]).toMatchObject({
      id: 'wiki-3',
      sourceId: 'src-evidence',
      sourceName: 'Evidence Book',
      runnerPage: 'wiki',
    })
  })
})
