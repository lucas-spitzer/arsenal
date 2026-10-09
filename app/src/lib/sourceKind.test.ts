import { describe, expect, it } from 'vitest'
import { mapSourceDisplay } from './foundryMappers'
import type { Source } from './workspaceApi'

function source(overrides: Partial<Source>): Source {
  return {
    id: 'src-1',
    workspace_id: 'ws-1',
    filename: 'notes.json',
    slug: 'notes',
    mime_type: 'application/json',
    storage_path: 'ws/notes/original/notes.json',
    file_hash: 'hash',
    file_size_bytes: 2048,
    source_metadata: {},
    status: 'ready',
    created_at: '2026-10-08T00:00:00Z',
    updated_at: '2026-10-08T00:00:00Z',
    ...overrides,
  }
}

describe('mapSourceDisplay source kind', () => {
  it('labels structured data sources and flags them', () => {
    const display = mapSourceDisplay(source({ source_kind: 'structured_data' }))

    expect(display.isStructuredData).toBe(true)
    expect(display.documentType).toBe('Structured data')
  })

  it('treats a source without a kind as a document', () => {
    const display = mapSourceDisplay(source({ mime_type: 'application/pdf', filename: 'book.pdf' }))

    expect(display.isStructuredData).toBe(false)
    expect(display.documentType).not.toBe('Structured data')
  })
})
