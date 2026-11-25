import { useCallback, useEffect, useRef, useState } from 'react'
import { useWorkspace } from '../../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../../features/workspace/workspaceDataContext'
import { sourceTitle } from '../../../lib/foundryMappers'
import {
  activeKnowledgeRunId,
  attachKnowledgeVisuals,
  createKnowledgeProject,
  deleteKnowledgeProject,
  getKnowledgeProject,
  listKnowledgeProjects,
  uploadPlanVisual,
  type KnowledgeDraftItem,
  type KnowledgeHome,
  type KnowledgeProjectDetail,
  type KnowledgeProjectSummary,
} from '../../../lib/knowledgeApi'
import { useLessons } from '../../../lib/useLessons'
import { ErrorBanner } from '../ErrorBanner'
import { FoundryDialog } from '../FoundryDialog'
import { Loader } from '../../shared/Loader'
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

function sourceTitleFor(source: Parameters<typeof sourceTitle>[0] | undefined): string {
  return source ? sourceTitle(source) : ''
}

/** The notes file name without its extension, else the book or class it belongs to. */
function projectTitle(files: File[], homeName: string): string {
  const notes = files.find((file) => file.name.toLowerCase().endsWith('.json')) ?? files[0]
  const fromFile = notes ? notes.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim() : ''
  return fromFile || homeName.trim() || 'Knowledge notes'
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
          <Loader label="Loading knowledge projects" size="sm" />
        ) : projects.length === 0 ? (
          <div className="as-console__empty">
            <p>No knowledge projects yet. Upload notes against an ingested book, or practice questions for a class.</p>
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
  const { lessons, isLoading: lessonsLoading } = useLessons(activeWorkspace?.id ?? null)
  const readySources = sources.filter((source) => source.status === 'ready')
  const [home, setHome] = useState<KnowledgeHome>({ kind: 'book', sourceId: readySources[0]?.id ?? '' })
  const [notes, setNotes] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const selectedLessonId = home.kind === 'lesson'
    ? lessons.find((lesson) => lesson.id === home.lessonId)?.id ?? lessons[0]?.id ?? ''
    : ''
  const homeReady = home.kind === 'book' ? home.sourceId.length > 0 : selectedLessonId.length > 0
  const hasContent = home.kind === 'lesson' ? files.length > 0 : files.length > 0 || notes.trim().length > 0
  const ready = homeReady && hasContent
  const homeName = home.kind === 'book'
    ? sourceTitleFor(readySources.find((source) => source.id === home.sourceId))
    : lessons.find((lesson) => lesson.id === selectedLessonId)?.title ?? ''

  const submit = async () => {
    if (!ready || !activeWorkspace) return
    const nextHome: KnowledgeHome = home.kind === 'book'
      ? home
      : { kind: 'lesson', lessonId: selectedLessonId }
    setIsSubmitting(true)
    setError(null)
    try {
      const project = await createKnowledgeProject(activeWorkspace.id, {
        title: projectTitle(files, homeName),
        home: nextHome,
        notes: notes.trim(),
        files,
      })
      onCreated(project.id)
    } catch (caught) {
      setError(errorMessage(caught, home.kind === 'lesson' ? 'Could not save the questions.' : 'Could not start structuring.'))
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
            {isSubmitting ? 'Starting…' : home.kind === 'lesson' ? 'Save questions' : 'Start structure'}
          </button>
        </div>
      </header>
      <div className="as-console__scroll kproj-setup">
        {error ? <ErrorBanner message={error} /> : null}
        <div className="kproj-field">
          <span className="kproj-label" id="kproj-home-label">
            Belongs to
          </span>
          <div className="kproj-switch" role="tablist" aria-labelledby="kproj-home-label">
            <button
              type="button"
              role="tab"
              aria-selected={home.kind === 'book'}
              className={home.kind === 'book' ? 'is-active' : undefined}
              onClick={() => {
                if (home.kind === 'book') return
                setHome({ kind: 'book', sourceId: readySources[0]?.id ?? '' })
                setFiles([])
                setNotes('')
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
            >
              Book
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={home.kind === 'lesson'}
              className={home.kind === 'lesson' ? 'is-active' : undefined}
              onClick={() => {
                if (home.kind === 'lesson') return
                setHome({ kind: 'lesson', lessonId: lessons[0]?.id ?? '' })
                setFiles([])
                setNotes('')
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
            >
              Class
            </button>
          </div>
          {home.kind === 'book' ? (
            <>
              <label className="kproj-label" htmlFor="kproj-source">
                Book
              </label>
              <select
                id="kproj-source"
                className="as-wiki__input kproj-select"
                value={home.sourceId}
                onChange={(event) => setHome({ kind: 'book', sourceId: event.target.value })}
              >
                {readySources.length === 0 ? <option value="">No ingested books</option> : null}
                {readySources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {sourceTitle(source)}
                  </option>
                ))}
              </select>
              <p className="dsn-hint">The book these notes belong to. A JSON file is stored with that book and written straight into the wiki.</p>
            </>
          ) : (
            <>
              <label className="kproj-label" htmlFor="kproj-source">
                Class
              </label>
              <select
                id="kproj-source"
                className="as-wiki__input kproj-select"
                value={selectedLessonId}
                onChange={(event) => setHome({ kind: 'lesson', lessonId: event.target.value })}
              >
                {lessons.length === 0 ? (
                  <option value="">{lessonsLoading ? 'Loading classes' : 'No classes yet'}</option>
                ) : null}
                {lessons.map((lesson) => (
                  <option key={lesson.id} value={lesson.id}>
                    {lesson.title}
                  </option>
                ))}
              </select>
              <p className="dsn-hint">
                Practice questions for this class. A question pack is JSON, or a zip of the JSON and the images. Terms,
                lists, ELOs, and abbreviations still go on a book. Study guides are not uploaded here yet.
              </p>
            </>
          )}
        </div>
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-file">
            {home.kind === 'lesson' ? 'JSON Data Upload' : 'Notes file'}
          </label>
          <div className="kproj-file">
            <input
              ref={fileInputRef}
              id="kproj-file"
              type="file"
              hidden
              multiple
              accept={home.kind === 'lesson' ? '.json,.png,.jpg,.jpeg,.webp,.zip' : '.json,.md,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.zip'}
              onChange={(event) => {
                const next = event.target.files ? Array.from(event.target.files) : []
                setFiles(next)
                if (next.length > 0) setNotes('')
              }}
            />
            <button type="button" className="as-console__cta as-console__cta--ghost" onClick={() => fileInputRef.current?.click()}>
              {home.kind === 'lesson' ? '⇪ Upload questions' : '⇪ Upload notes'}
            </button>
            {files.length > 0 ? <span className="kproj-file__name">{files.map((item) => item.name).join(', ')}</span> : null}
            {files.length > 0 ? (
              <button
                type="button"
                className="kproj-file__clear"
                onClick={() => {
                  setFiles([])
                  if (fileInputRef.current) fileInputRef.current.value = ''
                }}
              >
                Clear
              </button>
            ) : null}
          </div>
          <p className="dsn-hint">
            {home.kind === 'lesson'
              ? 'The image file name has to match the filename on the question.'
              : 'JSON with terms, key lists, and ELOs is imported as wiki entries. Other files are transcribed first. A question pack with pictures is a zip of the JSON and the images, or the JSON and the image files selected together. The image file name has to match the filename on the question.'}
          </p>
        </div>
        {home.kind === 'book' ? (
          <div className="kproj-field">
            <label className="kproj-label" htmlFor="kproj-notes">
              Or paste notes
            </label>
            <textarea
              id="kproj-notes"
              className="as-wiki__input kproj-notes"
              rows={8}
              value={notes}
              disabled={files.length > 0}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        ) : null}
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
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
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
        {error ? <ErrorBanner message={error} /> : <Loader label="Loading" size="sm" />}
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
            <Loader label={label} />
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
          {project.status === 'composing' || project.status === 'failed' ? (
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost dsn-cta--danger"
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </button>
          ) : null}
        </div>
      </header>
      <div className="as-console__scroll">
        <div className={project.status === 'ready' ? 'kproj-column' : undefined}>
          <h3 className="kproj-doc-title">{project.title}</h3>
          {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
          {project.error ? <ErrorBanner message={project.error} /> : null}
          {project.status === 'failed' ? (
            <p className="dsn-hint">Structuring failed. Start a new project to try the notes again.</p>
          ) : null}
          {project.status === 'composing' ? (
            <KnowledgeComposer project={project} onChange={setProject} onError={setError} />
          ) : null}
          {project.status === 'ready' ? (
            <ReviewView project={project} onChange={setProject} onError={setError} onDone={onBack} />
          ) : null}
        </div>
      </div>
      <FoundryDialog
        title="Delete knowledge draft"
        open={deleteOpen}
        onClose={() => {
          if (!isDeleting) setDeleteOpen(false)
        }}
      >
        <p className="as-console__confirm-copy">
          Delete "{project.title}"? Wiki entries already saved stay in the library.
        </p>
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => setDeleteOpen(false)}
            disabled={isDeleting}
            autoFocus
          >
            Cancel
          </button>
          <button
            type="button"
            className="as-console__cta"
            disabled={isDeleting}
            onClick={() => {
              if (isDeleting) return
              setIsDeleting(true)
              setError(null)
              void deleteKnowledgeProject(project.id)
                .then(() => {
                  void refresh()
                  onBack()
                })
                .catch((caught: unknown) => {
                  setError(errorMessage(caught, 'Could not delete.'))
                  setIsDeleting(false)
                  setDeleteOpen(false)
                })
            }}
          >
            {isDeleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </FoundryDialog>
    </>
  )
}

function ReviewView({
  project,
  onChange,
  onError,
  onDone,
}: {
  project: KnowledgeProjectDetail
  onChange: (project: KnowledgeProjectDetail) => void
  onError: (message: string) => void
  onDone: () => void
}) {
  const [isBusy, setIsBusy] = useState(false)
  const hasImage = project.items.some((item) => item.visual != null)
  const actionLabel = isBusy ? 'Saving…' : hasImage ? 'Update images' : 'Done'

  return (
    <div className="kproj-compose">
      <div className="kproj-switches">
        {hasImage ? null : (
          <p className="dsn-hint">These questions are saved. Images are optional.</p>
        )}
        <button
          type="button"
          className="as-console__cta"
          disabled={isBusy}
          onClick={() => {
            setIsBusy(true)
            void attachKnowledgeVisuals(project.id)
              .then((next) => {
                onChange(next)
                if (!hasImage) onDone()
              })
              .catch((caught: unknown) => onError(errorMessage(caught, 'Could not update images.')))
              .finally(() => setIsBusy(false))
          }}
        >
          {actionLabel}
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
