import { useCallback, useEffect, useRef, useState } from 'react'
import { useWorkspace } from '../../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../../features/workspace/workspaceDataContext'
import { sourceTitle } from '../../../lib/foundryMappers'
import {
  activeKnowledgeRunId,
  attachKnowledgeVisuals,
  createKnowledgeProject,
  getKnowledgeProject,
  listKnowledgeProjects,
  uploadPlanVisual,
  type KnowledgeDraftItem,
  type KnowledgeProjectDetail,
  type KnowledgeProjectSummary,
} from '../../../lib/knowledgeApi'
import { ErrorBanner } from '../ErrorBanner'
import { FoundryLoader } from '../FoundryLoader'
import { KnowledgeComposer } from './KnowledgeComposer'
import { RunSteps } from './RunSteps'

type KnowledgeView = { kind: 'list' } | { kind: 'setup' } | { kind: 'project'; id: string }

const POLL_MS = 3000
const KINDS = ['icon', 'diagram', 'example'] as const
const FLASHCARD_PLACEMENTS = [
  { value: 'back', label: 'Back, instead of the definition' },
  { value: 'front', label: 'Front, instead of the label' },
  { value: 'beside', label: 'Beside the text' },
] as const

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

export function KnowledgeWorkshop({ onShowStudy }: { onShowStudy: () => void }) {
  const [view, setView] = useState<KnowledgeView>({ kind: 'list' })
  if (view.kind === 'setup') {
    return <KnowledgeSetup onCancel={() => setView({ kind: 'list' })} onCreated={(id) => setView({ kind: 'project', id })} />
  }
  if (view.kind === 'project') {
    return (
      <KnowledgeProject
        projectId={view.id}
        onBack={() => setView({ kind: 'list' })}
        onShowStudy={onShowStudy}
      />
    )
  }
  return (
    <KnowledgeList
      onCreate={() => setView({ kind: 'setup' })}
      onOpen={(id) => setView({ kind: 'project', id })}
      onShowStudy={onShowStudy}
    />
  )
}

function ProductSwitch({ knowledge, onShowStudy }: { knowledge: boolean; onShowStudy: () => void }) {
  return (
    <div className="kproj-switch" role="tablist" aria-label="Forge Knowledge">
      <button type="button" role="tab" aria-selected={!knowledge} onClick={onShowStudy}>
        Study material
      </button>
      <button type="button" role="tab" aria-selected={knowledge} className="is-active">
        Knowledge
      </button>
    </div>
  )
}

function KnowledgeList({
  onCreate,
  onOpen,
  onShowStudy,
}: {
  onCreate: () => void
  onOpen: (id: string) => void
  onShowStudy: () => void
}) {
  const { activeWorkspace } = useWorkspace()
  const [projects, setProjects] = useState<KnowledgeProjectSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!activeWorkspace) return
    let cancelled = false
    listKnowledgeProjects(activeWorkspace.id)
      .then((rows) => {
        if (!cancelled) setProjects(rows)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught, 'Could not load knowledge projects.'))
      })
    return () => {
      cancelled = true
    }
  }, [activeWorkspace])

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Knowledge</div>
          <h2>Design Forge</h2>
        </div>
        <ProductSwitch knowledge onShowStudy={onShowStudy} />
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta" onClick={onCreate}>
            + New knowledge
          </button>
        </div>
      </header>
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
        {projects === null ? (
          <FoundryLoader label="Loading knowledge projects" size="sm" />
        ) : projects.length === 0 ? (
          <div className="as-console__empty">
            <p>No knowledge projects yet. Upload notes against an ingested book to draft study items.</p>
            <button type="button" className="as-console__cta" onClick={onCreate}>
              New knowledge
            </button>
          </div>
        ) : (
          <ul className="kproj-list">
            {projects.map((project) => (
              <li key={project.id}>
                <button type="button" className="kproj-list__item" onClick={() => onOpen(project.id)}>
                  <span>{project.title}</span>
                  <span className="kproj-list__status">{project.status}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

function KnowledgeSetup({ onCancel, onCreated }: { onCancel: () => void; onCreated: (id: string) => void }) {
  const { activeWorkspace } = useWorkspace()
  const { sources } = useWorkspaceData()
  const readySources = sources.filter((source) => source.status === 'ready')
  const [title, setTitle] = useState('')
  const [sourceId, setSourceId] = useState(readySources[0]?.id ?? '')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const ready = title.trim().length > 0 && sourceId.length > 0 && (file !== null || notes.trim().length > 0)

  const submit = async () => {
    if (!ready || !activeWorkspace) return
    setIsSubmitting(true)
    setError(null)
    try {
      const project = await createKnowledgeProject(activeWorkspace.id, {
        title: title.trim(),
        sourceId,
        notes: notes.trim(),
        file,
      })
      onCreated(project.id)
    } catch (caught) {
      setError(errorMessage(caught, 'Could not start structuring.'))
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Knowledge</div>
          <h2>Design Forge</h2>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="as-console__cta" disabled={!ready || isSubmitting} onClick={() => void submit()}>
            {isSubmitting ? 'Starting…' : 'Start structure'}
          </button>
        </div>
      </header>
      <div className="as-console__scroll kproj-setup">
        {error ? <ErrorBanner message={error} /> : null}
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-title">
            Title
          </label>
          <input id="kproj-title" className="as-wiki__input" value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-source">
            Book
          </label>
          <select id="kproj-source" className="as-wiki__input kproj-select" value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
            {readySources.length === 0 ? <option value="">No ingested sources</option> : null}
            {readySources.map((source) => (
              <option key={source.id} value={source.id}>
                {sourceTitle(source)}
              </option>
            ))}
          </select>
          <p className="dsn-hint">The book these notes belong to. A JSON file is stored with that book and written straight into the wiki.</p>
        </div>
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-file">
            Notes file
          </label>
          <div className="kproj-file">
            <input
              ref={fileInputRef}
              id="kproj-file"
              type="file"
              hidden
              accept=".json,.md,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null
                setFile(next)
                if (next) setNotes('')
              }}
            />
            <button type="button" className="as-console__cta as-console__cta--ghost" onClick={() => fileInputRef.current?.click()}>
              ⇪ Upload notes
            </button>
            {file ? <span className="kproj-file__name">{file.name}</span> : null}
            {file ? (
              <button
                type="button"
                className="kproj-file__clear"
                onClick={() => {
                  setFile(null)
                  if (fileInputRef.current) fileInputRef.current.value = ''
                }}
              >
                Clear
              </button>
            ) : null}
          </div>
          <p className="dsn-hint">
            JSON with terms and key_lists is imported as wiki entries. Other files are transcribed first.
          </p>
        </div>
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-notes">
            Or paste notes
          </label>
          <textarea
            id="kproj-notes"
            className="as-wiki__input kproj-notes"
            rows={8}
            value={notes}
            disabled={file !== null}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>
    </>
  )
}

function KnowledgeProject({
  projectId,
  onBack,
  onShowStudy,
}: {
  projectId: string
  onBack: () => void
  onShowStudy: () => void
}) {
  const { refresh } = useWorkspaceData()
  const [project, setProject] = useState<KnowledgeProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const status = project?.status

  const reload = useCallback(() => {
    getKnowledgeProject(projectId)
      .then(setProject)
      .catch((caught: unknown) => setError(errorMessage(caught, 'Could not load the project.')))
  }, [projectId])

  useEffect(reload, [reload])

  useEffect(() => {
    if (status !== 'structuring' && status !== 'drafting') return
    const intervalId = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(intervalId)
  }, [status, reload])

  useEffect(() => {
    if (status === 'composing' || status === 'ready' || status === 'failed') void refresh()
  }, [status, refresh])

  if (!project) {
    return (
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : <FoundryLoader label="Loading" size="sm" />}
      </div>
    )
  }

  const runId = activeKnowledgeRunId(project)
  if (project.status === 'structuring' || project.status === 'drafting') {
    const label = project.status === 'structuring' ? 'Structuring notes into wiki entries' : 'Drafting study items'
    return (
      <>
        <header className="as-console__header">
          <div>
            <div className="as-console__eyebrow">Knowledge</div>
            <h2>Design Forge</h2>
          </div>
          <div className="dsn-header-actions">
            <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onBack}>
              All projects
            </button>
          </div>
        </header>
        <div className="as-console__scroll">
          <h3 className="kproj-doc-title">{project.title}</h3>
          <section className="as-console__panel">
            <FoundryLoader label={label} />
            <p className="dsn-hint">Progress also shows in Production Operations.</p>
          </section>
          <RunSteps runId={runId} />
        </div>
      </>
    )
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Knowledge</div>
          <h2>Design Forge</h2>
        </div>
        <ProductSwitch knowledge onShowStudy={onShowStudy} />
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onBack}>
            All projects
          </button>
        </div>
      </header>
      <div className="as-console__scroll">
        <h3 className="kproj-doc-title">{project.title}</h3>
        {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
        {project.error ? <ErrorBanner message={project.error} /> : null}
        {project.status === 'failed' ? (
          <p className="dsn-hint">Structuring failed. Start a new project to try the notes again.</p>
        ) : null}
        {project.status === 'composing' ? (
          <KnowledgeComposer project={project} onChange={setProject} onError={setError} />
        ) : null}
        {project.status === 'ready' ? <ReviewView project={project} onChange={setProject} onError={setError} /> : null}
      </div>
    </>
  )
}

function ReviewView({
  project,
  onChange,
  onError,
}: {
  project: KnowledgeProjectDetail
  onChange: (project: KnowledgeProjectDetail) => void
  onError: (message: string) => void
}) {
  const [isBusy, setIsBusy] = useState(false)

  return (
    <div className="kproj-compose">
      <div className="kproj-switches">
        <button
          type="button"
          className="as-console__cta"
          disabled={isBusy}
          onClick={() => {
            setIsBusy(true)
            void attachKnowledgeVisuals(project.id)
              .then(onChange)
              .catch((caught: unknown) => onError(errorMessage(caught, 'Could not update images.')))
              .finally(() => setIsBusy(false))
          }}
        >
          Update images
        </button>
      </div>
      <ul className="kproj-entries">
        {project.items.map((item) => (
          <ReviewItem key={item.plan_id} projectId={project.id} item={item} onChange={onChange} onError={onError} />
        ))}
      </ul>
    </div>
  )
}

function ReviewItem({
  projectId,
  item,
  onChange,
  onError,
}: {
  projectId: string
  item: KnowledgeDraftItem
  onChange: (project: KnowledgeProjectDetail) => void
  onError: (message: string) => void
}) {
  const placement = item.item_type === 'flashcard' ? 'back' : item.item_type === 'question' ? 'stem' : 'situation'
  const [kind, setKind] = useState(item.visual?.kind ?? 'diagram')
  const [chosenPlacement, setChosenPlacement] = useState(item.visual?.placement ?? placement)
  const [alt, setAlt] = useState(item.visual?.alt ?? '')

  return (
    <li className="kproj-entry">
      <p className="kproj-entry__meta">{item.item_type}</p>
      <strong>{item.title}</strong>
      <p>{item.body}</p>
      {item.visual?.url ? <img src={item.visual.url} alt={item.visual.alt || item.title} /> : null}
      <div className="kproj-visual">
        <label>
          Kind
          <select className="as-wiki__input kproj-select" value={kind} onChange={(event) => setKind(event.target.value)}>
            {KINDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        {item.item_type === 'flashcard' ? (
          <label>
            Placement
            <select className="as-wiki__input kproj-select" value={chosenPlacement} onChange={(event) => setChosenPlacement(event.target.value)}>
              {FLASHCARD_PLACEMENTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="dsn-hint">{item.item_type === 'question' ? 'Shown above the question.' : 'Shown with the situation.'}</p>
        )}
        <label>
          Alt text
          <input className="as-wiki__input" value={alt} onChange={(event) => setAlt(event.target.value)} placeholder="Optional" />
        </label>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          aria-label={`Image for ${item.title}`}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (!file) return
            void uploadPlanVisual(projectId, item.plan_id, {
              file,
              kind,
              placement: item.item_type === 'flashcard' ? chosenPlacement : placement,
              alt,
            })
              .then(onChange)
              .catch((caught: unknown) => onError(errorMessage(caught, 'Could not upload the image.')))
          }}
        />
      </div>
    </li>
  )
}
