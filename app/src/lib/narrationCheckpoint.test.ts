import { describe, expect, it } from 'vitest'
import {
  narrationCheckpointCopy,
  narrationCheckpointsForSources,
  narrationRestartWarning,
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
    expect(checkpoints).toEqual([
      {
        sourceId: 'src-1',
        modelId: 'gemini-3.8-flash-tts',
        voiceId: 'Sadaltager',
        clipCount: 18,
        clipsTotal: 81,
        paragraphsSaved: null,
        paragraphsTotal: null,
      },
    ])
    expect(narrationCheckpointCopy(checkpoints[0])).toBe(
      '18 of 81 clips of gemini-3.8-flash-tts (Sadaltager) narration are already saved. Continue synthesizes only what is missing.',
    )
  })

  it('uses paragraph counts so split clips still count as partial', () => {
    const checkpoints = narrationCheckpointsForSources(
      [
        artifact({
          manifest: {
            status: 'complete',
            voice_id: 'Charon',
            model_id: 'gemini-3.8-flash-tts',
            clip_count: 40,
            clips_total: 34,
            paragraphs_saved: 213,
            paragraphs_total: 223,
          },
        }),
      ],
      ['src-1'],
      'Charon',
      'gemini-3.8-flash-tts',
    )
    expect(checkpoints).toHaveLength(1)
    expect(narrationRestartWarning(checkpoints)).toBe(
      'Start over permanently deletes 213 of 223 paragraphs of gemini-3.8-flash-tts (Charon) narration and synthesizes everything again, using new TTS credits and daily quota. This cannot be undone.',
    )
  })

  it('skips narration with every paragraph saved', () => {
    const checkpoints = narrationCheckpointsForSources(
      [
        artifact({
          manifest: {
            voice_id: 'Charon',
            model_id: 'gemini-3.8-flash-tts',
            clip_count: 30,
            clips_total: 34,
            paragraphs_saved: 223,
            paragraphs_total: 223,
          },
        }),
      ],
      ['src-1'],
      'Charon',
      'gemini-3.8-flash-tts',
    )
    expect(checkpoints).toEqual([])
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
