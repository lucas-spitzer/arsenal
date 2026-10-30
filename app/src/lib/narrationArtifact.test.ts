import { describe, expect, it, vi } from 'vitest'

vi.mock('../features/auth/authService', () => ({
  getAccessToken: async () => null,
}))

import {
  artifactLibraryCard,
  isIncompleteNarrationArtifact,
  narrationDownloadState,
  outputChipLabel,
} from './academyOutputs'
import {
  collapseDuplicateNarrationArtifacts,
  narrationArtifactStatusLabel,
  narrationSegmentProgress,
  pipelineStepDetail,
  productionRunParagraphsMissing,
  stageRunSummary,
} from './foundryMappers'
import type { Artifact, PipelineStep, StageRun } from './workspaceApi'

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

  it('counts reused clips plus new clips, not skipped attempts', () => {
    const stageRun: StageRun = {
      id: 'sr-1',
      production_run_id: 'run-2',
      workspace_id: 'ws-1',
      stage_id: 'generate-narration',
      stage_version: '1.0',
      module: 'mathesys',
      status: 'failed',
      inputs: {},
      output: {
        summary: '52/81 clips',
        segments_done: 52,
        segments_total: 81,
        segments_reused: 18,
        segments_narrated: 18,
        segments_skipped: 16,
      },
      promoted: null,
      model: null,
      token_usage: null,
      api_usage: null,
      cost_usd: 0,
      error: '429 RESOURCE_EXHAUSTED',
      started_at: '2026-10-07T13:32:00Z',
      completed_at: '2026-10-07T14:39:00Z',
    }

    expect(narrationSegmentProgress(stageRun)).toEqual({ done: 36, total: 81 })
    expect(stageRunSummary(stageRun)).toBe('36/81 clips')
    expect(productionRunParagraphsMissing([stageRun])).toBe(0)

    const gaps: StageRun = {
      ...stageRun,
      status: 'completed',
      output: {
        ...stageRun.output,
        segments_reused: 34,
        segments_narrated: 0,
        segments_total: 34,
        paragraphs_total: 223,
        paragraphs_saved: 213,
        paragraphs_missing: 10,
      },
    }
    expect(stageRunSummary(gaps)).toBe('34/34 clips · Incomplete: 10 paragraphs missing')
    expect(productionRunParagraphsMissing([stageRun, gaps])).toBe(10)

    const step: PipelineStep = {
      step: 'generate-narration',
      type: 'stage',
      status: 'pending',
      stage_id: 'generate-narration',
    }
    expect(pipelineStepDetail(step, [step], [stageRun], 'failed')).toBe('36/81 clips')
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
        artifact({ artifact_type: 'study_material', manifest: { status: 'in_progress' } }),
      ),
    ).toBe(false)
  })

  it('shows one Library card for duplicate narration.json rows from failed restarts', () => {
    const rows = [1, 2, 3, 4].map((n) =>
      artifact({
        id: `art-${n}`,
        production_run_id: `run-${n}`,
        created_at: `2026-01-0${n}T00:00:00Z`,
        manifest: { voice_id: 'Kore', model_id: 'gemini-3.8-flash-tts' },
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

describe('narration download state', () => {
  it('stays absent until a combined file or a prepare job exists', () => {
    expect(narrationDownloadState({})).toBe('absent')
    expect(narrationDownloadState({ combined_audio_status: 'preparing' })).toBe('preparing')
    expect(narrationDownloadState({ combined_audio_status: 'failed' })).toBe('failed')
    expect(narrationDownloadState({ combined_audio_path: 'audio/book.mp3' })).toBe('ready')
  })
})

describe('library artifact cards', () => {
  it('names narration by duration, not the voice or json filename', () => {
    expect(
      artifactLibraryCard(
        artifact({
          filename: 'narration.json',
          manifest: {
            voice_id: 'Hugh_32',
            total_duration_seconds: 7860,
          },
        }),
      ),
    ).toMatchObject({
      chipLabel: 'Audio',
      title: '2h 11m',
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

  it('names ebooks by count and study material by title', () => {
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
          artifact_type: 'study_material',
          source_id: null,
          format: 'pdf',
          filename: 'material.pdf',
          manifest: { title: 'Land Navigation', template_name: 'Branded Sheet' },
        }),
      ),
    ).toMatchObject({ chipLabel: 'Material', title: 'Land Navigation', isStudyMaterial: true })
  })

  it('names an uploaded mp3 as an Audiobook', () => {
    const card = artifactLibraryCard(
      artifact({
        artifact_type: 'audiobook',
        format: 'mp3',
        filename: 'Warfighting.mp3',
        manifest: { title: 'Warfighting' },
      }),
    )
    expect(card).toMatchObject({
      chipLabel: 'Audiobook',
      title: 'Warfighting',
      isAudiobook: true,
      isNarration: false,
      isAudio: true,
    })
    expect(
      outputChipLabel({
        kind: 'audio',
        id: 'art-1',
        title: 'Warfighting',
        sourceId: 'src-1',
        sourceName: 'Warfighting',
        footer: 'Warfighting',
        badge: 'MP3',
        createdAt: '2026-01-01T00:00:00Z',
        runnerPage: null,
        isAudio: true,
        isEbook: false,
        isNarration: false,
        isAudiobook: true,
        narrationDownload: null,
        projectId: null,
      }),
    ).toBe('Audiobook')
  })
})
