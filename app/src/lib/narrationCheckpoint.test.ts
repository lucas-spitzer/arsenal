import { describe, expect, it } from 'vitest'
import {
  narrationCheckpointCopy,
  narrationCheckpointsForSources,
  narrationRunPayload,
  narrationVoiceModel,
} from './narrationCheckpoint'
import type { Artifact, StageSetting } from './workspaceApi'

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
    manifest: {
      status: 'in_progress',
      voice_id: 'Sadaltager',
      model_id: 'gemini-3.8-flash-tts',
      clip_count: 18,
      clips_total: 81,
    },
    created_at: '2026-10-04T03:50:00Z',
    ...overrides,
  }
}

function narrationSetting(overrides: Partial<StageSetting> = {}): StageSetting {
  return {
    stage_action: 'audio_narration',
    label: 'Audio Narration',
    provider: 'google',
    model: 'gemini-3.8-flash-tts',
    reasoning_effort: null,
    reasoning_tokens: null,
    voice_id: 'Sadaltager',
    image_quality: null,
    is_overridden: true,
    default_provider: 'google',
    default_model: 'gemini-3.8-flash-tts',
    default_voice_id: 'Sadaltager',
    default_image_quality: null,
    ...overrides,
  }
}

describe('narration checkpoint dialog', () => {
  it('opens for a partial narration that matches the current voice and model', () => {
    const voice = narrationVoiceModel([narrationSetting()])
    expect(voice).toEqual({ voiceId: 'Sadaltager', modelId: 'gemini-3.8-flash-tts' })
    const checkpoints = narrationCheckpointsForSources(
      [artifact()],
      ['src-1'],
      voice?.voiceId ?? '',
      voice?.modelId ?? '',
    )
    expect(checkpoints).toEqual([{ sourceId: 'src-1', clipCount: 18, clipsTotal: 81 }])
    expect(narrationCheckpointCopy(checkpoints[0])).toBe(
      '18 of 81 clips are already saved. Continue will synthesize only the missing clips. Start over deletes those clips and synthesizes the book again.',
    )
  })

  it('does not offer continue for a different voice', () => {
    const checkpoints = narrationCheckpointsForSources(
      [artifact()],
      ['src-1'],
      'Kore',
      'gemini-3.8-flash-tts',
    )
    expect(checkpoints).toEqual([])
  })

  it('continue submits no restart ids and start over submits the source', () => {
    expect(
      narrationRunPayload({
        sourceIds: ['src-1'],
        targetArtifacts: ['narration_audio'],
        restartSourceIds: [],
      }),
    ).toEqual({
      source_ids: ['src-1'],
      target_artifacts: ['narration_audio'],
    })
    expect(
      narrationRunPayload({
        sourceIds: ['src-1'],
        targetArtifacts: ['narration_audio'],
        restartSourceIds: ['src-1'],
      }),
    ).toEqual({
      source_ids: ['src-1'],
      target_artifacts: ['narration_audio'],
      narration_restart_source_ids: ['src-1'],
    })
  })
})
