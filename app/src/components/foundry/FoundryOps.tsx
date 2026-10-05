import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { formatDateTime, formatDuration, formatCostUsd, statusLabel } from '../../lib/foundryFormat'
import {
  flattenApiRequests,
  productionRunCostUsd,
  productionRunDurationSec,
  productionRunLabel,
  productionRunProgress,
  stageRunTokens,
  sumWorkspaceCostUsd,
} from '../../lib/foundryMappers'
import { FoundryDetail } from './FoundryDetail'
import { FoundryDialog } from './FoundryDialog'
import { ErrorBanner } from './ErrorBanner'
import { NewRunPanel } from './NewRunPanel'

interface FoundryOpsProps {
  onGoToSources: () => void
}

type RunDeletePrompt =
  | { kind: 'idle' }
  | { kind: 'menu'; runId: string; x: number; y: number }
  | { kind: 'confirm'; runId: string }

function isNode(value: EventTarget | null): value is Node {
  return value instanceof Node
}

export function FoundryOps({ onGoToSources }: FoundryOpsProps) {
  const {
    sources,
    productionRuns,
    stageRunsByRunId,
    activeRunCount,
    isLoading,
    error,
    deleteProductionRun,
  } = useWorkspaceData()

  const sortedRuns = useMemo(
    () => [...productionRuns].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [productionRuns],
  )

  const [activeId, setActiveId] = useState<string | null>(null)
  const [showNewRun, setShowNewRun] = useState(false)
  const [deletePrompt, setDeletePrompt] = useState<RunDeletePrompt>({ kind: 'idle' })
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sortedRuns.length) {
      setActiveId(null)
      return
    }
    if (!activeId || !sortedRuns.some((run) => run.id === activeId)) {
      setActiveId(sortedRuns[0].id)
    }
  }, [sortedRuns, activeId])

  useEffect(() => {
    if (deletePrompt.kind !== 'menu') return
    const close = (event: MouseEvent) => {
      const target = event.target
      if (isNode(target) && menuRef.current?.contains(target)) return
      setDeletePrompt({ kind: 'idle' })
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDeletePrompt({ kind: 'idle' })
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [deletePrompt])

  const active = sortedRuns.find((run) => run.id === activeId) ?? null
  const confirmRun =
    deletePrompt.kind === 'confirm'
      ? sortedRuns.find((run) => run.id === deletePrompt.runId) ?? null
      : null

  const confirmDelete = async () => {
    if (deletePrompt.kind !== 'confirm' || isDeleting) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await deleteProductionRun(deletePrompt.runId)
      setDeletePrompt({ kind: 'idle' })
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : 'Could not delete this run.')
    } finally {
      setIsDeleting(false)
    }
  }

  const metrics = useMemo(() => {
    const completed = productionRuns.filter((run) => run.status === 'completed').length
    const failed = productionRuns.filter((run) => run.status === 'failed').length
    const finished = completed + failed
    const successRate = finished ? Math.round((completed / finished) * 100) : 0

    const durations = productionRuns
      .filter((run) => run.completed_at)
      .map((run) => productionRunDurationSec(run))
    const avgDuration =
      durations.length > 0
        ? formatDuration(Math.round(durations.reduce((sum, d) => sum + d, 0) / durations.length))
        : '—'

    let totalTokens = 0
    for (const runs of Object.values(stageRunsByRunId)) {
      for (const stageRun of runs) {
        const tokens = stageRunTokens(stageRun)
        totalTokens += tokens.in + tokens.out
      }
    }

    const totalCost = sumWorkspaceCostUsd(productionRuns, stageRunsByRunId)

    return [
      { label: 'Active runs', value: String(activeRunCount), delta: '', trend: 'flat' as const },
      { label: 'Pipeline runs', value: String(productionRuns.length), delta: '', trend: 'flat' as const },
      { label: 'Success rate', value: finished ? `${successRate}%` : '—', delta: '', trend: 'flat' as const },
      {
        label: 'Tokens used',
        value: totalTokens > 1_000_000 ? `${(totalTokens / 1_000_000).toFixed(1)}M` : `${Math.round(totalTokens / 1000)}K`,
        delta: '',
        trend: 'flat' as const,
      },
      {
        label: 'Total API cost',
        value: formatCostUsd(totalCost),
        delta: '',
        trend: 'flat' as const,
      },
      { label: 'Avg run time', value: avgDuration, delta: '', trend: 'flat' as const },
    ]
  }, [productionRuns, activeRunCount, stageRunsByRunId])

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Mission Control</div>
          <h2>Production Operations</h2>
        </div>
        {activeRunCount > 0 ? (
          <span className="as-console__live">
            <span className="as-live-dot" /> Live · {activeRunCount} run{activeRunCount === 1 ? '' : 's'} active
          </span>
        ) : (
          <span className="as-console__live" style={{ opacity: 0.6 }}>
            Idle
          </span>
        )}
        <button className="as-console__cta" onClick={() => setShowNewRun(true)}>
          + New run
        </button>
      </header>

      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}
        {showNewRun ? (
          <NewRunPanel onClose={() => setShowNewRun(false)} onCreated={() => setShowNewRun(false)} />
        ) : null}

        <div className="as-console__metrics">
          {metrics.map((metric) => (
            <div className="as-console__metric" key={metric.label}>
              <div className="l">{metric.label}</div>
              <div className="v">{metric.value}</div>
              {metric.delta ? <div className={`d as-${metric.trend}`}>{metric.delta}</div> : null}
            </div>
          ))}
        </div>

        {isLoading && sortedRuns.length === 0 ? (
          <div className="as-console__empty">Loading production runs…</div>
        ) : sortedRuns.length === 0 ? (
          <div className="as-console__empty">
            No production runs yet.{' '}
            {sources.length === 0 ? (
              <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onGoToSources}>
                Upload a source
              </button>
            ) : (
              <button type="button" className="as-console__cta as-console__cta--ghost" onClick={() => setShowNewRun(true)}>
                Start your first run
              </button>
            )}
          </div>
        ) : (
          <div className="as-console__split">
            <section className="as-console__panel">
              <div className="as-console__panel-head">
                <h3>Pipeline runs</h3>
                <span className="as-count">{sortedRuns.length}</span>
              </div>
              {sortedRuns.map((run) => {
                const progress = productionRunProgress(run, stageRunsByRunId[run.id] ?? [])
                const apiRequestCount = flattenApiRequests([run], stageRunsByRunId, sources).length
                const runCost = productionRunCostUsd(run, stageRunsByRunId[run.id] ?? [])
                return (
                  <button
                    key={run.id}
                    className={`as-console__runrow${run.id === activeId ? ' is-active' : ''}`}
                    onClick={() => setActiveId(run.id)}
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setActiveId(run.id)
                      setDeletePrompt({
                        kind: 'menu',
                        runId: run.id,
                        x: Math.min(event.clientX, window.innerWidth - 180),
                        y: Math.min(event.clientY, window.innerHeight - 48),
                      })
                    }}
                  >
                    <span className={`as-dot as-dot--${run.status}`} />
                    <span>
                      <div className="title">{productionRunLabel(run, sources)}</div>
                      <div className="sub">
                        {run.id.slice(0, 8).toUpperCase()} · {apiRequestCount} API requests
                        {runCost > 0 ? ` · ${formatCostUsd(runCost)}` : ''} ·{' '}
                        {formatDateTime(run.created_at)}
                      </div>
                      {run.status === 'running' || run.status === 'queued' ? (
                        <div className="as-console__progress">
                          <span style={{ width: `${progress}%` }} />
                        </div>
                      ) : null}
                    </span>
                    <span className="right">
                      <span className={`as-console__statepill as-state--${run.status}`}>
                        {statusLabel(run.status)}
                      </span>
                    </span>
                  </button>
                )
              })}
            </section>

            {active ? (
              <FoundryDetail run={active} />
            ) : (
              <section className="as-console__panel">
                <div className="as-console__empty">Select a run to view details.</div>
              </section>
            )}
          </div>
        )}
      </div>

      {deletePrompt.kind === 'menu' ? (
        <div
          ref={menuRef}
          className="as-console__menu"
          role="menu"
          style={{ left: deletePrompt.x, top: deletePrompt.y }}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => setDeletePrompt({ kind: 'confirm', runId: deletePrompt.runId })}
          >
            Delete run
          </button>
        </div>
      ) : null}

      <FoundryDialog
        title="Delete run"
        open={deletePrompt.kind === 'confirm'}
        onClose={() => {
          if (!isDeleting) setDeletePrompt({ kind: 'idle' })
        }}
      >
        {deleteError ? <ErrorBanner message={deleteError} /> : null}
        <p className="as-console__confirm-copy">
          Delete {confirmRun ? productionRunLabel(confirmRun, sources) : 'this run'}? This removes
          the run, its stage runs, and the artifacts it created. Uploaded sources stay.
        </p>
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => setDeletePrompt({ kind: 'idle' })}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button type="button" className="as-console__cta" onClick={() => void confirmDelete()} disabled={isDeleting}>
            {isDeleting ? 'Deleting…' : 'Delete run'}
          </button>
        </div>
      </FoundryDialog>
    </>
  )
}
