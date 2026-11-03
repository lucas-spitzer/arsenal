import { describe, expect, it } from 'vitest'
import { mapSourceDisplay } from './foundryMappers'
import { sourceDisplayName } from './sourceDisplay'
import type { Source } from './workspaceApi'

function source(overrides: Partial<Source> = {}): Source {
  return {
    id: 'src-1',
    workspace_id: 'ws-1',
    filename: 'notes.pdf',
    slug: 'notes',
    mime_type: 'application/pdf',
    storage_path: 'ws/notes/notes.pdf',
    file_hash: 'hash',
    file_size_bytes: 2048,
    source_metadata: {},
    status: 'ready',
    created_at: '2026-10-08T00:00:00Z',
    updated_at: '2026-10-08T00:00:00Z',
    ...overrides,
  }
}

describe('sourceDisplayName', () => {
  it('prefers an explicit display name over the filename', () => {
    expect(
      sourceDisplayName(
        source({
          filename: 'source',
          source_metadata: { display_name: 'MCDP 1 Warfighting' },
        }),
      ),
    ).toBe('MCDP 1 Warfighting')
  })

  it('uses the filename stem when no display name is set', () => {
    expect(sourceDisplayName(source())).toBe('notes')
  })
})

describe('mapSourceDisplay awaiting file', () => {
  it('shows the background and hides file size', () => {
    const display = mapSourceDisplay(
      source({
        filename: 'Warfighting',
        mime_type: 'application/x-pending',
        storage_path: '',
        file_hash: 'pending:src-1',
        file_size_bytes: 0,
        status: 'awaiting_file',
        source_metadata: {
          display_name: 'MCDP 1 Warfighting',
          background: 'Doctrine for maneuver warfare.',
          document_type: 'Doctrinal publication',
          issuing_authority: 'US Marine Corps',
        },
      }),
    )

    expect(display.title).toBe('MCDP 1 Warfighting')
    expect(display.purpose).toBe('Doctrine for maneuver warfare.')
    expect(display.documentType).toBe('Doctrinal publication')
    expect(display.issuingAuthority).toBe('US Marine Corps')
    expect(display.sizeLabel).toBe('—')
    expect(display.mimeLabel).toBe('—')
    expect(display.status).toBe('awaiting_file')
  })
})
