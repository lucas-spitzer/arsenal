import { describe, expect, it, vi } from 'vitest'
import type { Block } from './readerContent'

vi.mock('./sourcesApi', () => ({
  listAllSourceSegments: vi.fn(),
  listSourceChapters: vi.fn(),
  listSourceNarration: vi.fn(),
}))

import type { NarrationSegment } from './sourcesApi'
import { listSourceNarration } from './sourcesApi'
import {
  clearReaderCache,
  isAbortError,
  liveAfterMissingScope,
  loadReaderDocument,
  loadReaderNarration,
  narrationFailureWarning,
  narrationMapFromRows,
  readReaderCache,
  shouldResumeReaderLoad,
  writeReaderCache,
} from './readerLoad'

function block(id: string): Block {
  return {
    seq: 0,
    id,
    kind: 'paragraph',
    level: 0,
    text: 'Hello.',
    md: null,
    chapterTitle: 'Chapter',
    isChapterStart: false,
  }
}

function narrationRow(segmentId: string, words: NarrationSegment['words']): NarrationSegment {
  return {
    id: segmentId,
    source_id: 'source-1',
    workspace_id: 'workspace-1',
    chapter_id: null,
    segment_id: segmentId,
    provider: 'eleven',
    voice_id: 'voice-1',
    model_id: 'eleven_v3',
    text_hash: 'hash',
    duration_seconds: 1,
    words,
    alignment_source: 'estimated',
    alignment_quality: {},
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('loadReaderDocument', () => {
  it('publishes blocks while narration is still pending', async () => {
    let releaseNarration: (value: {
      narration: Map<string, NarrationSegment>
      warning: string | null
    }) => void = () => {}
    const narration = new Promise<{
      narration: Map<string, NarrationSegment>
      warning: string | null
    }>((resolve) => {
      releaseNarration = resolve
    })
    const onText = vi.fn()
    const onNarration = vi.fn()
    const pending = loadReaderDocument({
      loadText: async () => [block('p1')],
      loadNarration: () => narration,
      onText,
      onNarration,
      signal: new AbortController().signal,
    })

    await vi.waitFor(() => expect(onText).toHaveBeenCalledOnce())
    expect(onNarration).not.toHaveBeenCalled()

    const ready = { narration: new Map<string, NarrationSegment>(), warning: null }
    releaseNarration(ready)
    await pending
    expect(onNarration).toHaveBeenCalledWith(ready)
  })

  it('keeps the published blocks when narration returns a warning', async () => {
    const onText = vi.fn()
    const onNarration = vi.fn()
    const warning = narrationFailureWarning(new Error('offline'))
    await loadReaderDocument({
      loadText: async () => [block('p1')],
      loadNarration: async () => ({ narration: new Map(), warning }),
      onText,
      onNarration,
      signal: new AbortController().signal,
    })
    expect(onText).toHaveBeenCalledWith([expect.objectContaining({ id: 'p1' })])
    expect(onNarration).toHaveBeenCalledWith({ narration: new Map(), warning })
  })
})

describe('loadReaderNarration', () => {
  it('returns a warning instead of throwing when narration fails', async () => {
    vi.mocked(listSourceNarration).mockRejectedValueOnce(new Error('offline'))
    const result = await loadReaderNarration('workspace-1', 'source-1', new AbortController().signal)
    expect(result.narration.size).toBe(0)
    expect(result.warning).toBe(narrationFailureWarning(new Error('offline')))
  })
})

describe('narrationMapFromRows', () => {
  it('drops rows that have no word timings', () => {
    const map = narrationMapFromRows([
      narrationRow('bare', []),
      narrationRow('timed', [{ i: 0, w: 'Hello.', s: 0, e: 0.4 }]),
    ])
    expect([...map.keys()]).toEqual(['timed'])
  })
})

describe('liveAfterMissingScope', () => {
  it('clears a stuck loading flag when the workspace disappears', () => {
    expect(liveAfterMissingScope({ loading: true, blocks: [block('p1')] })).toEqual({
      loading: false,
      blocks: [block('p1')],
    })
  })

  it('leaves a finished load alone', () => {
    const live = { loading: false, error: null }
    expect(liveAfterMissingScope(live)).toBe(live)
  })
})

describe('shouldResumeReaderLoad', () => {
  it('retries a load that is still open or died while the tab was hidden', () => {
    expect(shouldResumeReaderLoad({ visible: true, loading: true, failedWhileHidden: false })).toBe(
      true,
    )
    expect(shouldResumeReaderLoad({ visible: true, loading: false, failedWhileHidden: true })).toBe(
      true,
    )
    expect(shouldResumeReaderLoad({ visible: false, loading: true, failedWhileHidden: true })).toBe(
      false,
    )
    expect(
      shouldResumeReaderLoad({ visible: true, loading: false, failedWhileHidden: false }),
    ).toBe(false)
  })
})

describe('reader cache', () => {
  it('returns a book after it has been stored', () => {
    clearReaderCache()
    const entry = {
      blocks: [block('p1')],
      narration: new Map<string, NarrationSegment>(),
      narrationWarning: null,
    }
    writeReaderCache('workspace-1', 'source-1', entry)
    expect(readReaderCache('workspace-1', 'source-1')).toEqual(entry)
    expect(readReaderCache('workspace-1', 'other')).toBeNull()
    clearReaderCache()
  })
})

describe('isAbortError', () => {
  it('recognizes an aborted fetch', () => {
    expect(isAbortError(new DOMException('aborted', 'AbortError'))).toBe(true)
    expect(isAbortError(new Error('nope'))).toBe(false)
  })
})
