import { useWorkspaceData } from '../../../features/workspace/workspaceDataContext'
import {
  pipelineStepDetail,
  pipelineStepDisplayStatus,
  pipelineStepLabel,
} from '../../../lib/foundryMappers'

/** The same step list OPS shows for this run, fed by the workspace poll. */
export function RunSteps({ runId }: { runId: string | null }) {
  const { productionRuns, stageRunsByRunId } = useWorkspaceData()
  const run = runId ? productionRuns.find((item) => item.id === runId) : undefined
  if (!run) return null
  const stageRuns = stageRunsByRunId[run.id] ?? []

  return (
    <ol className="dsn-steps" aria-label="Run progress">
      {run.pipeline.map((step) => {
        const status = pipelineStepDisplayStatus(step, run.pipeline, stageRuns, run.status)
        return (
          <li className="as-console__step" key={step.step}>
            <span className={`as-console__step-dot as-console__step-dot--${status}`} aria-hidden="true">
              {status === 'completed' ? '✓' : status === 'failed' ? '✕' : '•'}
            </span>
            <div className="as-console__step-body">
              <div className="name">
                {pipelineStepLabel(step)} <span className="sr-only">({status})</span>
              </div>
              <div className="desc">{pipelineStepDetail(step, run.pipeline, stageRuns, run.status)}</div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
