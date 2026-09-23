import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { useLiveTick } from '../../hooks/useLiveTick'
import {
  artifactFormatLabel,
  formatCostUsd,
  formatDuration,
  statusLabel,
} from '../../lib/foundryFormat'
import {
  artifactCardTitle,
  pipelineStepDetail,
  pipelineStepDisplayStatus,
  pipelineStepLabel,
  productionRunCostUsd,
  productionRunDurationSec,
  productionRunLabel,
  productionRunProgress,
  productionRunTargetLabel,
  collapseDuplicateNarrationArtifacts,
  narrationArtifactStatusLabel,
  narrationSegmentProgress,
} from '../../lib/foundryMappers'
import type { ProductionRun } from '../../lib/workspaceApi'
import { pipelineStepModuleLabel } from './moduleLabel'

interface FoundryDetailProps {
  run: ProductionRun
}

export function FoundryDetail({ run }: FoundryDetailProps) {
  const { sources, stageRunsByRunId, artifacts, wikiEntries, downloadArtifact } = useWorkspaceData()
  const stageRuns = stageRunsByRunId[run.id] ?? []
  const runArtifacts = collapseDuplicateNarrationArtifacts(artifacts).filter(
    (artifact) => artifact.production_run_id === run.id,
  )
  const sourceById = new Map(sources.map((source) => [source.id, source]))
  const hasLiveDuration =
    run.status === 'queued' ||
    run.status === 'running' ||
    stageRuns.some((stageRun) => stageRun.status === 'queued' || stageRun.status === 'running')
  useLiveTick(hasLiveDuration)
  const progress = productionRunProgress(run, stageRuns)
  const durationSec = productionRunDurationSec(run)
  const runCost = productionRunCostUsd(run, stageRuns)

  return (
    <section className="as-console__panel">
      <div className="as-console__panel-head">
        <h3>Run detail</h3>
        <span className="as-count">{run.id.slice(0, 8).toUpperCase()}</span>
      </div>
      <div className="as-console__detail">
        <h4>{productionRunLabel(run, sources)}</h4>
        <div className="meta">
          {statusLabel(run.status)} · {formatDuration(durationSec)} · {progress}% complete
          {runCost > 0 ? ` · ${formatCostUsd(runCost)}` : ''}
          {run.target_artifacts.length
            ? ` · ${productionRunTargetLabel(run.target_artifacts)}`
            : ' · Upload'}
        </div>

        {run.error ? (
          <div
            className="as-console__chip"
            style={{
              borderColor: 'var(--color-scarlet)',
              color: '#ff8b8b',
              background: 'rgba(148,0,0,0.16)',
              marginTop: 14,
            }}
          >
            ⚠ {run.error}
          </div>
        ) : null}

        <div style={{ height: 18 }} />

        {run.pipeline.map((step) => {
          const displayStatus = pipelineStepDisplayStatus(step, run.pipeline, stageRuns, run.status)
          const activeStageRun =
            step.stage_id
              ? stageRuns.find(
                  (stageRun) =>
                    stageRun.stage_id === step.stage_id &&
                    (stageRun.status === 'running' || stageRun.status === 'queued'),
                )
              : undefined
          const narrationProgress =
            step.step === 'generate-narration' && activeStageRun
              ? narrationSegmentProgress(activeStageRun)
              : null
          const narrationPct = narrationProgress
            ? Math.min(100, Math.round((narrationProgress.done / narrationProgress.total) * 100))
            : 0
          return (
            <div className="as-console__step" key={step.step}>
              <span className={`as-console__step-dot as-console__step-dot--${displayStatus}`}>
                {displayStatus === 'completed' ? '✓' : displayStatus === 'failed' ? '✕' : '•'}
              </span>
              <div className="as-console__step-body">
                <div className="name">
                  {pipelineStepLabel(step)}{' '}
                  {step.module ? (
                    <span className="as-console__module-tag">{pipelineStepModuleLabel(step)}</span>
                  ) : null}
                </div>
                <div className="desc">
                  {pipelineStepDetail(step, run.pipeline, stageRuns, run.status)}
                </div>
                {narrationProgress ? (
                  <div className="as-console__progress as-console__progress--step" title={`${narrationProgress.done}/${narrationProgress.total} clips`}>
                    <span style={{ width: `${narrationPct}%` }} />
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}

        {runArtifacts.length > 0 ? (
          <>
            <div className="as-console__panel-head" style={{ padding: '4px 0', borderBottom: 0 }}>
              <h3 style={{ fontSize: '0.86rem' }}>Artifacts</h3>
            </div>
            {runArtifacts.map((artifact) => {
              const source = artifact.source_id ? sourceById.get(artifact.source_id) : undefined

              return (
              <button
                type="button"
                className="as-console__artifact"
                key={artifact.id}
                onClick={() => void downloadArtifact(artifact.id)}
              >
                <span className="ic">{artifactFormatLabel(artifact.format)}</span>
                <span>
                  <div className="t">{artifactCardTitle(artifact, source)}</div>
                  <div className="s">
                    {narrationArtifactStatusLabel(artifact)
                      ?? artifact.filename}
                  </div>
                </span>
              </button>
              )
            })}
          </>
        ) : null}

        {wikiEntries.length > 0 ? (
          <>
            <div className="as-console__panel-head" style={{ padding: '14px 0 4px', borderBottom: 0 }}>
              <h3 style={{ fontSize: '0.86rem' }}>Wiki entries · {wikiEntries.length}</h3>
            </div>
            <div className="as-console__chips">
              {wikiEntries.slice(0, 8).map((entry) => (
                <span className="as-console__chip" key={entry.id}>
                  {entry.preferred_label}
                  <span style={{ opacity: 0.65, marginLeft: 6 }}>{entry.entry_kind}</span>
                </span>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </section>
  )
}
