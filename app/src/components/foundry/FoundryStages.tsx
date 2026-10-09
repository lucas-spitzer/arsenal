import { useMemo, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { useLiveTick } from '../../hooks/useLiveTick'
import {
  formatCostUsd,
  formatCredits,
  formatDate,
  formatDateTime,
  formatDuration,
  statusLabel,
} from '../../lib/foundryFormat'
import {
  flattenApiRequests,
  stageRunApiToolLabel,
  stageRunCostUsd,
  stageRunCredits,
  stageRunDisplayName,
  stageRunDurationSec,
  stageRunSummary,
  stageRunTokens,
} from '../../lib/foundryMappers'
import { FoundryDialog } from './FoundryDialog'
import { FoundryLoader } from './FoundryLoader'
import { FoundryViewToggle } from './FoundryViewToggle'
import { ErrorBanner } from './ErrorBanner'
import { moduleLabel } from './moduleLabel'
import type { FoundryView } from './types'

function formatTokenUsage(stageRun: Parameters<typeof stageRunTokens>[0]): string {
  const tokens = stageRunTokens(stageRun)
  const total = tokens.in + tokens.out
  if (total > 0) return `${(total / 1000).toFixed(1)}K`

  return '—'
}

export function FoundryStages() {
  const { productionRuns, stageRunsByRunId, sources, isLoading, error } = useWorkspaceData()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<FoundryView>('grid')
  const [errorStageId, setErrorStageId] = useState<string | null>(null)

  const apiRequests = useMemo(
    () => flattenApiRequests(productionRuns, stageRunsByRunId, sources),
    [productionRuns, stageRunsByRunId, sources],
  )

  const hasLiveDuration = apiRequests.some(
    (stageRun) => stageRun.status === 'queued' || stageRun.status === 'running',
  )
  useLiveTick(hasLiveDuration)

  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    return apiRequests.filter(
      (stageRun) =>
        stageRunDisplayName(stageRun).toLowerCase().includes(q) ||
        stageRunApiToolLabel(stageRun).toLowerCase().includes(q) ||
        stageRun.stage_id.includes(q) ||
        stageRun.runLabel.toLowerCase().includes(q) ||
        moduleLabel(stageRun.module).toLowerCase().includes(q),
    )
  }, [apiRequests, query])

  const errorStage = useMemo(
    () => (errorStageId ? apiRequests.find((stageRun) => stageRun.id === errorStageId) : undefined),
    [errorStageId, apiRequests],
  )

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Execution Log</div>
          <h2>API Requests</h2>
        </div>
        <FoundryViewToggle view={view} onChange={setView} />
      </header>
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}
        <div className="as-console__searchbar">
          <span style={{ color: '#6f828b' }}>⌕</span>
          <input
            placeholder="Search API requests by stage, tool, module, or production run…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span className="as-count">{filtered.length} requests</span>
        </div>
        {isLoading && filtered.length === 0 ? (
          <div className="as-console__empty">
            <FoundryLoader label="Loading API requests" size="sm" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="as-console__empty">No API requests yet. Start a production run from OPS.</div>
        ) : view === 'list' ? (
          <section className="as-console__panel">
            <table className="as-console__table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Tool</th>
                  <th>Module</th>
                  <th>Status</th>
                  <th>Runtime</th>
                  <th>Tokens</th>
                  <th>Credits</th>
                  <th>Cost</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((stageRun) => {
                  const costUsd = stageRunCostUsd(stageRun)
                  return (
                    <tr key={stageRun.id}>
                      <td>
                        <div className="as-console__listname">
                          <span>
                            <div className="t">{stageRunDisplayName(stageRun)}</div>
                            <div className="s">
                              {stageRun.started_at ? formatDateTime(stageRun.started_at) : '—'}
                            </div>
                          </span>
                        </div>
                      </td>
                      <td>{stageRunApiToolLabel(stageRun)}</td>
                      <td>{moduleLabel(stageRun.module)}</td>
                      <td>
                        <span className={`as-console__statepill as-state--${stageRun.status}`}>
                          {statusLabel(stageRun.status)}
                        </span>
                      </td>
                      <td className="num">{formatDuration(stageRunDurationSec(stageRun))}</td>
                      <td className="num">{formatTokenUsage(stageRun)}</td>
                      <td className="num">{formatCredits(stageRunCredits(stageRun))}</td>
                      <td className="num">{formatCostUsd(costUsd)}</td>
                      <td>{stageRun.runId.slice(0, 8).toUpperCase()}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>
        ) : (
          <div className="as-console__sources">
            {filtered.map((stageRun) => {
              const tokens = stageRunTokens(stageRun)
              const costUsd = stageRunCostUsd(stageRun)
              const credits = stageRunCredits(stageRun)
              return (
                <div
                  className="as-console__panel as-console__artifact-card as-console__stage-card"
                  key={stageRun.id}
                  style={{ padding: 18 }}
                >
                  <div>
                    <div style={{ fontFamily: 'var(--as-grotesk)', fontWeight: 600, color: '#fff' }}>
                      {stageRunDisplayName(stageRun)}{' '}
                      <span className="as-console__module-tag">{moduleLabel(stageRun.module)}</span>
                    </div>
                    <div
                      style={{
                        fontFamily: 'var(--as-mono)',
                        fontSize: '0.7rem',
                        color: '#8aa1ab',
                        marginTop: 3,
                      }}
                    >
                      {stageRunApiToolLabel(stageRun)} · v{stageRun.stage_version}
                    </div>
                  </div>
                  <p style={{ fontSize: '0.84rem', color: '#b6c4cb', marginTop: 12, lineHeight: 1.5 }}>
                    {stageRunSummary(stageRun)}
                  </p>
                  <div className="stats">
                    <span>{formatDuration(stageRunDurationSec(stageRun))}</span>
                    {tokens.in + tokens.out > 0 ? (
                      <span>{((tokens.in + tokens.out) / 1000).toFixed(1)}K tok</span>
                    ) : null}
                    {credits > 0 ? <span>{formatCredits(credits)} cr</span> : null}
                    {costUsd > 0 ? <span>{formatCostUsd(costUsd)}</span> : null}
                  </div>
                  {stageRun.error ? (
                    <button
                      type="button"
                      className="as-console__error-trigger"
                      onClick={() => setErrorStageId(stageRun.id)}
                    >
                      Show error message
                    </button>
                  ) : null}
                  <div className="as-console__card-fill" aria-hidden="true" />
                  <div className="as-console__artifact-foot">
                    <span className="seg">
                      {stageRun.started_at ? formatDate(stageRun.started_at) : '—'}
                    </span>
                    <span className="seg">{stageRun.runId.slice(0, 8).toUpperCase()}</span>
                    <span className="seg">
                      <span className={`as-console__statepill as-state--${stageRun.status}`}>
                        {statusLabel(stageRun.status)}
                      </span>
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
      <FoundryDialog
        title={errorStage ? `${stageRunDisplayName(errorStage)} error` : 'API request error'}
        open={errorStageId !== null && Boolean(errorStage?.error)}
        onClose={() => setErrorStageId(null)}
      >
        <pre className="as-console__error-detail">{errorStage?.error}</pre>
      </FoundryDialog>
    </>
  )
}
