import { Boxes } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { formatDate, statusLabel } from '../../lib/foundryFormat'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'
import { FoundryLoader } from './FoundryLoader'

export function FoundryWorkspaces() {
  const { activeWorkspace, workspaces, isLoading, error, selectWorkspace, createWorkspace } =
    useWorkspace()
  const {
    sources,
    artifacts,
    productionRuns,
    wikiEntries,
    flashcards,
    quizzes,
    scenarios,
    activeRunCount,
  } = useWorkspaceData()
  const [isCreating, setIsCreating] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [workspaceName, setWorkspaceName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const overview = useMemo(
    () => [
      { label: 'Sources', value: String(sources.length) },
      { label: 'Artifacts', value: String(artifacts.length) },
      { label: 'Wiki entries', value: String(wikiEntries.length) },
      { label: 'Pipeline runs', value: String(productionRuns.length) },
      { label: 'Active runs', value: String(activeRunCount) },
      {
        label: 'Assessments',
        value: String(flashcards.length + quizzes.length + scenarios.length),
      },
    ],
    [
      sources.length,
      artifacts.length,
      wikiEntries.length,
      productionRuns.length,
      activeRunCount,
      flashcards.length,
      quizzes.length,
      scenarios.length,
    ],
  )

  const openCreate = () => {
    setWorkspaceName('')
    setCreateError(null)
    setCreateOpen(true)
  }

  const closeCreate = () => {
    if (isCreating) return
    setCreateOpen(false)
  }

  const handleCreate = async () => {
    const name = workspaceName.trim()
    if (!name || isCreating) return
    setIsCreating(true)
    setCreateError(null)
    try {
      await createWorkspace(name)
      setCreateOpen(false)
      setWorkspaceName('')
    } catch (caught) {
      setCreateError(caught instanceof Error ? caught.message : 'Failed to create workspace.')
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Environment</div>
          <h2>Workspaces</h2>
        </div>
        <span className="as-console__live">
          <span className="as-live-dot" /> {workspaces.length} available
        </span>
        <button type="button" className="as-console__cta" onClick={openCreate} disabled={isCreating}>
          {isCreating ? 'Creating…' : '+ New workspace'}
        </button>
      </header>

      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}

        {activeWorkspace ? (
          <div className="as-console__metrics">
            {overview.map((metric) => (
              <div className="as-console__metric" key={metric.label}>
                <div className="l">{metric.label}</div>
                <div className="v">{metric.value}</div>
                <div className="d as-flat">{activeWorkspace.name}</div>
              </div>
            ))}
          </div>
        ) : null}

        {isLoading && workspaces.length === 0 ? (
          <div className="as-console__empty">
            <FoundryLoader label="Loading workspaces" size="sm" />
          </div>
        ) : workspaces.length === 0 ? (
          <div className="as-console__empty">
            No workspaces yet. Create one to begin production.
          </div>
        ) : (
          <div className="as-console__sources">
            {workspaces.map((workspace) => {
              const isActive = workspace.id === activeWorkspace?.id
              return (
                <button
                  type="button"
                  key={workspace.id}
                  className={`as-console__panel as-console__ws-card${isActive ? ' is-active' : ''}`}
                  onClick={() => selectWorkspace(workspace.id)}
                  aria-pressed={isActive}
                >
                  <div className="as-console__ws-card-head">
                    <span className="as-console__ws-icon" aria-hidden="true">
                      <Boxes size={16} strokeWidth={1.75} />
                    </span>
                    <span className="as-console__ws-title">{workspace.name}</span>
                    {isActive ? <span className="as-console__ws-badge">Active</span> : null}
                  </div>
                  <p className="as-console__ws-desc">
                    {workspace.description?.trim() || 'No description provided.'}
                  </p>
                  <div className="as-console__card-fill" aria-hidden="true" />
                  <div className="as-console__artifact-foot">
                    <span className="seg">{statusLabel(workspace.status)}</span>
                    <span className="seg">{formatDate(workspace.created_at)}</span>
                    <span className="seg">{isActive ? 'Selected' : 'Set active'}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      <FoundryDialog title="New workspace" open={createOpen} onClose={closeCreate}>
        <form
          className="as-console__dialog-form"
          onSubmit={(event) => {
            event.preventDefault()
            void handleCreate()
          }}
        >
          {createError ? <ErrorBanner message={createError} /> : null}
          <label className="as-console__field-label" htmlFor="new-workspace-name">
            Name
          </label>
          <input
            id="new-workspace-name"
            className="as-wiki__input"
            value={workspaceName}
            onChange={(event) => setWorkspaceName(event.target.value)}
            autoFocus
            disabled={isCreating}
          />
          <div className="as-console__dialog-actions">
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              onClick={closeCreate}
              disabled={isCreating}
            >
              Cancel
            </button>
            <button type="submit" className="as-console__cta" disabled={isCreating || !workspaceName.trim()}>
              {isCreating ? 'Creating…' : 'Create workspace'}
            </button>
          </div>
        </form>
      </FoundryDialog>
    </>
  )
}
