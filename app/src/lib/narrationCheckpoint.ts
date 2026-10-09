import type { Artifact, StageSetting } from './workspaceApi'

export const AUDIO_NARRATION_ACTION = 'audio_narration'

export interface NarrationCheckpoint {
  sourceId: string
  clipCount: number
  clipsTotal: number
}

export interface NarrationRunPayload {
  source_ids: string[]
  target_artifacts: string[]
  narration_restart_source_ids?: string[]
}

export function narrationVoiceModel(
  settings: StageSetting[],
): { voiceId: string; modelId: string } | null {
  const setting = settings.find((row) => row.stage_action === AUDIO_NARRATION_ACTION)
  if (!setting?.voice_id || !setting.model) return null
  return { voiceId: setting.voice_id, modelId: setting.model }
}

function manifestText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function manifestCount(value: unknown): number | null {
  const count = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(count)) return null
  return count
}

function isNewerArtifact(candidate: Artifact, current: Artifact): boolean {
  if (candidate.created_at !== current.created_at) {
    return candidate.created_at > current.created_at
  }
  return candidate.id > current.id
}

/** Partial narration for the voice and model the next run will use. */
export function narrationCheckpointsForSources(
  artifacts: Artifact[],
  sourceIds: string[],
  voiceId: string,
  modelId: string,
): NarrationCheckpoint[] {
  const selected = new Set(sourceIds)
  const newest = new Map<string, Artifact>()

  for (const artifact of artifacts) {
    if (artifact.artifact_type !== 'narration_audio' || !artifact.source_id) continue
    if (!selected.has(artifact.source_id)) continue
    if (manifestText(artifact.manifest.voice_id) !== voiceId) continue
    if (manifestText(artifact.manifest.model_id) !== modelId) continue
    const current = newest.get(artifact.source_id)
    if (!current || isNewerArtifact(artifact, current)) {
      newest.set(artifact.source_id, artifact)
    }
  }

  const checkpoints: NarrationCheckpoint[] = []
  for (const artifact of newest.values()) {
    if (!artifact.source_id) continue
    const clipCount = manifestCount(artifact.manifest.clip_count)
    const clipsTotal = manifestCount(artifact.manifest.clips_total)
    if (clipCount === null || clipsTotal === null) continue
    if (clipCount <= 0 || clipCount >= clipsTotal) continue
    checkpoints.push({
      sourceId: artifact.source_id,
      clipCount,
      clipsTotal,
    })
  }
  return checkpoints
}

export function narrationCheckpointCopy(checkpoint: NarrationCheckpoint): string {
  return `${checkpoint.clipCount} of ${checkpoint.clipsTotal} clips are already saved. Continue will synthesize only the missing clips. Start over deletes those clips and synthesizes the book again.`
}

export function narrationRunPayload(args: {
  sourceIds: string[]
  targetArtifacts: string[]
  restartSourceIds: string[]
}): NarrationRunPayload {
  const payload: NarrationRunPayload = {
    source_ids: args.sourceIds,
    target_artifacts: args.targetArtifacts,
  }
  if (args.restartSourceIds.length > 0) {
    payload.narration_restart_source_ids = args.restartSourceIds
  }
  return payload
}
