import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./apiClient', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from './apiClient'
import { listSourceNarration, narrationPagePath, type NarrationSegment } from './sourcesApi'

const request = vi.mocked(apiRequest)

function narrationRow(id: string): NarrationSegment {
  return {
    id,
    source_id: 'source-1',
    workspace_id: 'workspace-1',
    chapter_id: null,
    segment_id: id,
    provider: 'eleven',
    voice_id: 'voice-1',
    model_id: 'eleven_v3',
    text_hash: 'hash',
    duration_seconds: 1,
    words: [],
    alignment_source: 'provider',
    alignment_quality: {},
    created_at: '2026-01-01T00:00:00Z',
  }
}

beforeEach(() => {
  request.mockReset()
})

describe('narrationPagePath', () => {
  it('adds the voice only after the first page has one', () => {
    expect(narrationPagePath('workspace-1', 'source-1', { limit: 2000, offset: 0 })).toBe(
      '/workspaces/workspace-1/sources/source-1/narration?limit=2000&offset=0',
    )
    expect(
      narrationPagePath('workspace-1', 'source-1', {
        limit: 2000,
        offset: 2000,
        modelId: 'eleven_v3',
        voiceId: 'voice-1',
      }),
    ).toBe(
      '/workspaces/workspace-1/sources/source-1/narration?limit=2000&offset=2000&model_id=eleven_v3&voice_id=voice-1',
    )
  })
})

describe('listSourceNarration', () => {
  it('sends the first page voice on the next page and forwards the abort signal', async () => {
    const first = Array.from({ length: 2000 }, (_, index) => narrationRow(`row-${index}`))
    request.mockResolvedValueOnce(first).mockResolvedValueOnce([narrationRow('tail')])
    const controller = new AbortController()

    const rows = await listSourceNarration('workspace-1', 'source-1', { signal: controller.signal })

    expect(rows).toHaveLength(2001)
    expect(request).toHaveBeenNthCalledWith(
      1,
      '/workspaces/workspace-1/sources/source-1/narration?limit=2000&offset=0',
      { signal: controller.signal },
    )
    expect(request).toHaveBeenNthCalledWith(
      2,
      '/workspaces/workspace-1/sources/source-1/narration?limit=2000&offset=2000&model_id=eleven_v3&voice_id=voice-1',
      { signal: controller.signal },
    )
  })
})
