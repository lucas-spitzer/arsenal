import type { Artifact, StageSetting } from './workspaceApi'

export const AUDIO_NARRATION_ACTION = 'audio_narration'

export interface NarrationCheckpoint {
  sourceId: string
  modelId: string
  voiceId: string
  clipCount: number
  clipsTotal: number
  paragraphsSaved: number | null
  paragraphsTotal: number | null
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
  if (value === null || value === undefined || value === '') return null
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

function isPartial(
  clipCount: number,
  clipsTotal: number,
  paragraphsSaved: number | null,
  paragraphsTotal: number | null,
): boolean {
  if (paragraphsSaved !== null && paragraphsTotal !== null && paragraphsTotal > 0) {
    return paragraphsSaved > 0 && paragraphsSaved < paragraphsTotal
  }
  return clipCount > 0 && clipCount < clipsTotal
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
    const paragraphsSaved = manifestCount(artifact.manifest.paragraphs_saved)
    const paragraphsTotal = manifestCount(artifact.manifest.paragraphs_total)
    if (!isPartial(clipCount, clipsTotal, paragraphsSaved, paragraphsTotal)) continue
    checkpoints.push({
      sourceId: artifact.source_id,
      modelId,
      voiceId,
      clipCount,
      clipsTotal,
      paragraphsSaved,
      paragraphsTotal,
    })
  }
  return checkpoints
}

function savedAmount(checkpoint: NarrationCheckpoint): string {
  if (checkpoint.paragraphsSaved !== null && checkpoint.paragraphsTotal !== null) {
    return `${checkpoint.paragraphsSaved} of ${checkpoint.paragraphsTotal} paragraphs`
  }
  return `${checkpoint.clipCount} of ${checkpoint.clipsTotal} clips`
}

function voiceLabel(checkpoint: NarrationCheckpoint): string {
  return `${checkpoint.modelId} (${checkpoint.voiceId})`
}

export function narrationCheckpointCopy(checkpoint: NarrationCheckpoint): string {
  return `${savedAmount(checkpoint)} of ${voiceLabel(checkpoint)} narration are already saved. Continue synthesizes only what is missing.`
}

export function narrationCheckpointLine(checkpoint: NarrationCheckpoint): string {
  return `${savedAmount(checkpoint)} saved for ${voiceLabel(checkpoint)}`
}

/** Shown before Start over deletes saved audio; the deletion cannot be undone. */
export function narrationRestartWarning(checkpoints: NarrationCheckpoint[]): string {
  const first = checkpoints[0]
  if (!first) return ''
  const amount =
    checkpoints.length === 1
      ? savedAmount(first)
      : `the saved audio for ${checkpoints.length} sources`
  return `Start over permanently deletes ${amount} of ${voiceLabel(first)} narration and synthesizes everything again, using new TTS credits and daily quota. This cannot be undone.`
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
