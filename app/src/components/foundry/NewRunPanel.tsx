import { useEffect, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { sourceTitle } from '../../lib/foundryMappers'
import {
  narrationCheckpointCopy,
  narrationCheckpointsForSources,
  narrationRunPayload,
  narrationVoiceModel,
  type NarrationCheckpoint,
} from '../../lib/narrationCheckpoint'
import { ARTIFACT_OPTIONS, getStageSettings, type StageSetting } from '../../lib/workspaceApi'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'

interface NewRunPanelProps {
  onClose: () => void
  onCreated: () => void
}

export function NewRunPanel({ onClose, onCreated }: NewRunPanelProps) {
  const { activeWorkspace } = useWorkspace()
  const { sources, artifacts, createProductionRun } = useWorkspaceData()
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([])
  const [selectedArtifacts, setSelectedArtifacts] = useState<string[]>([])
  const [stageSettings, setStageSettings] = useState<StageSetting[] | null>(null)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [checkpoints, setCheckpoints] = useState<NarrationCheckpoint[] | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    const workspaceId = activeWorkspace?.id
    if (!workspaceId) return
    let cancelled = false
    void getStageSettings(workspaceId)
      .then((settings) => {
        if (!cancelled) setStageSettings(settings)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setSettingsError(
            caught instanceof Error ? caught.message : 'Failed to load narration settings.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [activeWorkspace?.id])

  const toggleSource = (id: string) => {
    setSelectedSourceIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )
  }

  const toggleArtifact = (value: string) => {
    setSelectedArtifacts((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    )
  }

  const startRun = async (restartSourceIds: string[]) => {
    setIsSubmitting(true)
    setSubmitError(null)
    try {
      await createProductionRun(
        narrationRunPayload({
          sourceIds: selectedSourceIds,
          targetArtifacts: selectedArtifacts,
          restartSourceIds,
        }),
      )
      onCreated()
      onClose()
    } catch (caught) {
      setSubmitError(caught instanceof Error ? caught.message : 'Failed to create production run.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmit = () => {
    if (!selectedSourceIds.length) {
      setSubmitError('Select at least one source.')
      return
    }
    if (!selectedArtifacts.includes('narration_audio')) {
      void startRun([])
      return
    }
    if (settingsError) {
      setSubmitError(settingsError)
      return
    }
    if (!stageSettings) {
      setSubmitError('Narration settings are still loading.')
      return
    }
    const voice = narrationVoiceModel(stageSettings)
    const partial = voice
      ? narrationCheckpointsForSources(
          artifacts,
          selectedSourceIds,
          voice.voiceId,
          voice.modelId,
        )
      : []
    if (partial.length > 0) {
      setCheckpoints(partial)
      return
    }
    void startRun([])
  }

  const checkpoint = checkpoints?.[0]

  return (
    <section className="as-console__panel" style={{ marginBottom: 'var(--space-5)' }}>
      <div className="as-console__panel-head">
        <h3>New production run</h3>
        <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
      <div style={{ padding: '0 18px 18px' }}>
        {sources.length === 0 ? (
          <p className="as-console__empty">Upload a source before starting a production run.</p>
        ) : (
          <>
            <p className="as-console__field-label">Sources</p>
            <div className="as-console__chips" style={{ marginBottom: 20 }}>
              {sources.map((source) => (
                <button
                  key={source.id}
                  type="button"
                  className={`as-console__chip${selectedSourceIds.includes(source.id) ? ' is-active' : ''}`}
                  onClick={() => toggleSource(source.id)}
                >
                  {sourceTitle(source)}
                </button>
              ))}
            </div>

            <p className="as-console__field-label">Artifacts</p>
            <div className="as-console__chips" style={{ marginBottom: 20 }}>
              {ARTIFACT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`as-console__chip${selectedArtifacts.includes(option.value) ? ' is-active' : ''}`}
                  onClick={() => toggleArtifact(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {submitError ? <ErrorBanner message={submitError} /> : null}
            <button
              type="button"
              className="as-console__cta as-console__run-submit"
              disabled={isSubmitting}
              onClick={handleSubmit}
            >
              {isSubmitting ? 'Starting…' : 'Start run'}
            </button>
          </>
        )}
      </div>

      <FoundryDialog
        title="Saved narration"
        open={checkpoint !== undefined}
        onClose={() => {
          if (!isSubmitting) setCheckpoints(null)
        }}
      >
        {submitError ? <ErrorBanner message={submitError} /> : null}
        {checkpoints && checkpoints.length > 1 ? (
          <ul className="as-console__confirm-copy">
            {checkpoints.map((item) => {
              const source = sources.find((row) => row.id === item.sourceId)
              const title = source ? sourceTitle(source) : 'This source'
              return (
                <li key={item.sourceId}>
                  {title}: {item.clipCount} of {item.clipsTotal} clips
                </li>
              )
            })}
          </ul>
        ) : null}
        <p className="as-console__confirm-copy">
          {checkpoints && checkpoints.length > 1
            ? 'Continue will synthesize only the missing clips. Start over deletes those clips and synthesizes them again.'
            : checkpoint
              ? narrationCheckpointCopy(checkpoint)
              : ''}
        </p>
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => setCheckpoints(null)}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => void startRun(checkpoints?.map((item) => item.sourceId) ?? [])}
            disabled={isSubmitting}
          >
            Start over
          </button>
          <button
            type="button"
            className="as-console__cta"
            onClick={() => void startRun([])}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Starting…' : 'Continue'}
          </button>
        </div>
      </FoundryDialog>
    </section>
  )
}
