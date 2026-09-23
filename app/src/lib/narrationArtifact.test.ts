import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import { artifactLibraryCard, isIncompleteNarrationArtifact } from './academyOutputs'
import {
  collapseDuplicateNarrationArtifacts,
  narrationArtifactStatusLabel,
} from './foundryMappers'
import type { Artifact } from './workspaceApi'

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: 'art-1',
    workspace_id: 'ws-1',
    source_id: 'src-1',
    production_run_id: 'run-1',
    artifact_type: 'narration_audio',
    format: 'json',
    filename: 'narration.json',
    storage_path: 'ws/src/narration.json',
    file_size_bytes: 10,
    manifest: {},
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('narration artifact progress', () => {
  it('labels in-progress Foundry cards with the clip fraction', () => {
    expect(
      narrationArtifactStatusLabel(
        artifact({
          manifest: { status: 'in_progress', clip_count: 10, clips_total: 82 },
        }),
      ),
    ).toBe('In progress · 10/82 clips')
  })

  it('hides the label once narration is complete', () => {
    expect(
      narrationArtifactStatusLabel(
        artifact({ manifest: { status: 'complete', clip_count: 82, clips_total: 82 } }),
      ),
    ).toBeNull()
  })

  it('omits in-progress narration from Academy Library outputs', () => {
    expect(
      isIncompleteNarrationArtifact(
        artifact({ manifest: { status: 'in_progress' } }),
      ),
    ).toBe(true)
    expect(
      isIncompleteNarrationArtifact(
        artifact({ manifest: { status: 'complete' } }),
      ),
    ).toBe(false)
    expect(
      isIncompleteNarrationArtifact(
        artifact({ artifact_type: 'study_sheet', manifest: { status: 'in_progress' } }),
      ),
    ).toBe(false)
  })

  it('shows one Library card for duplicate narration.json rows from failed restarts', () => {
    const rows = [1, 2, 3, 4].map((n) =>
      artifact({
        id: `art-${n}`,
        production_run_id: `run-${n}`,
        created_at: `2026-01-0${n}T00:00:00Z`,
        manifest: { voice_id: 'Kore', model_id: 'gemini-3.1-flash-tts-preview' },
      }),
    )
    const visible = collapseDuplicateNarrationArtifacts(rows).filter(
      (row) => !isIncompleteNarrationArtifact(row),
    )
    expect(visible.map((row) => row.id)).toEqual(['art-4'])
  })

  it('keeps a separate card for a different voice or model', () => {
    const google = artifact({
      id: 'google',
      manifest: { voice_id: 'Kore', model_id: 'gemini' },
    })
    const speechify = artifact({
      id: 'speechify',
      manifest: { voice_id: 'henry', model_id: 'simba-english' },
    })
    expect(
      collapseDuplicateNarrationArtifacts([google, speechify]).map((row) => row.id),
    ).toEqual(['google', 'speechify'])
  })
})

describe('library artifact cards', () => {
  it('names audio with voice and duration, not the json filename', () => {
    expect(
      artifactLibraryCard(
        artifact({
          filename: 'narration.json',
          manifest: {
            voice_id: 'Kore',
            total_duration_seconds: 4320,
          },
        }),
      ),
    ).toMatchObject({
      chipLabel: 'Audio',
      title: 'Kore · 1h 12m',
      isNarration: true,
    })
  })

  it('hides opaque voice ids and still shows duration', () => {
    expect(
      artifactLibraryCard(
        artifact({
          manifest: {
            voice_id: '21m00Tcm4TlvDq8ikWAM',
            total_duration_seconds: 90,
          },
        }),
      ).title,
    ).toBe('1m 30s')
  })

  it('names ebooks and study sheets by count', () => {
    expect(
      artifactLibraryCard(
        artifact({
          artifact_type: 'electronic_book',
          format: 'epub3',
          filename: 'book.epub',
          manifest: { title: 'A New Conception of War: John Boyd', chapter_count: 12 },
        }),
      ),
    ).toMatchObject({ chipLabel: 'Book', title: '12 chapters', isEbook: true })

    expect(
      artifactLibraryCard(
        artifact({
          artifact_type: 'study_sheet',
          format: 'pdf',
          filename: 'sheet.pdf',
          manifest: { title: 'Warfighting', page_count: 8 },
        }),
      ),
    ).toMatchObject({ chipLabel: 'Sheet', title: '8 pages', isStudySheet: true })
  })
})
