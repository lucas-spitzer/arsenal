import { describe, expect, it } from 'vitest'
import { isApiRequestStageRun, stageRunApiToolLabel } from './foundryMappers'
import type { StageRun } from './workspaceApi'

function stageRun(overrides: Partial<StageRun> = {}): StageRun {
  return {
    id: 'sr-1',
    production_run_id: 'run-1',
    workspace_id: 'ws-1',
    stage_id: 'generate-narration',
    stage_version: '1.0',
    module: 'mathesys',
    status: 'failed',
    inputs: {},
    output: null,
    promoted: null,
    model: null,
    token_usage: null,
    api_usage: null,
    cost_usd: 0,
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:01:00Z',
    ...overrides,
  }
}

describe('API request capture', () => {
  it('keeps a failed ElevenLabs narration that only recorded the model on output', () => {
    const run = stageRun({
      output: { model_id: 'eleven_v3', character_count: 99852 },
    })
    expect(isApiRequestStageRun(run)).toBe(true)
    expect(stageRunApiToolLabel(run)).toBe('ElevenLabs')
  })

  it('labels Google TTS from the model id instead of the chat Gemini name', () => {
    const run = stageRun({
      status: 'completed',
      model: 'gemini-3.8-flash-tts',
      api_usage: {
        calls: [{ provider: 'google', model: 'gemini-3.8-flash-tts', character_count: 1000 }],
      },
    })
    expect(stageRunApiToolLabel(run)).toBe('Google TTS')
  })

  it('labels Cartesia, Speechify, and image models from the call that ran', () => {
    expect(
      stageRunApiToolLabel(
        stageRun({
          model: 'sonic-3.6',
          api_usage: { calls: [{ provider: 'cartesia', model: 'sonic-3.6' }] },
        }),
      ),
    ).toBe('Cartesia')
    expect(
      stageRunApiToolLabel(
        stageRun({
          model: 'simba-3.2',
          api_usage: { calls: [{ provider: 'speechify', model: 'simba-3.2' }] },
        }),
      ),
    ).toBe('Speechify')
    expect(
      stageRunApiToolLabel(
        stageRun({
          stage_id: 'generate-images',
          status: 'completed',
          model: 'gemini-3.1-flash-image',
          api_usage: { calls: [{ provider: 'google', model: 'gemini-3.1-flash-image' }] },
        }),
      ),
    ).toBe('Gemini Image')
    expect(
      stageRunApiToolLabel(
        stageRun({
          stage_id: 'generate-images',
          status: 'failed',
          model: 'gpt-image-2.5-sunburst',
        }),
      ),
    ).toBe('OpenAI Image')
  })

  it('shows Google TTS and the ElevenLabs alignment call on the same narration', () => {
    const run = stageRun({
      status: 'completed',
      model: 'gemini-3.8-flash-tts',
      api_usage: {
        calls: [
          { provider: 'google', model: 'gemini-3.8-flash-tts', character_count: 4000 },
          { provider: 'elevenlabs', model: 'forced-alignment', request_count: 3 },
        ],
      },
    })
    expect(stageRunApiToolLabel(run)).toBe('Google TTS · ElevenLabs')
  })

  it('leaves a narration that never reached the provider out of the log', () => {
    const run = stageRun({
      error: 'SPEECHIFY_API_KEY is not configured; cannot generate narration.',
      inputs: { model_id: 'simba-3.2' },
    })
    expect(isApiRequestStageRun(run)).toBe(false)
  })
})
