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
import {
  IMAGE_ACCEPT,
  MAX_QUESTION_IMAGES,
  imageStatus,
  mergeImages,
  questionImageNames,
} from '../../../lib/questionPackImages'
import { useLessons } from '../../../lib/useLessons'
import { ErrorBanner } from '../ErrorBanner'
import { FoundryDialog } from '../FoundryDialog'
import { Loader } from '../../shared/Loader'
import { KnowledgeComposer } from './KnowledgeComposer'
import { RunSteps } from './RunSteps'

type KnowledgeView = { kind: 'list' } | { kind: 'setup' } | { kind: 'project'; id: string }

const POLL_MS = 3000
const EVERY_CLASS = 'every-class'
// Vercel Functions reject request bodies over 4.5 MB.
const MAX_REQUEST_BYTES = 4.5 * 1024 * 1024
const KINDS = ['icon', 'diagram', 'example'] as const
const FLASHCARD_PLACEMENTS = [
  { value: 'back', label: 'Back, instead of the definition' },
  { value: 'front', label: 'Front, instead of the label' },
  { value: 'beside', label: 'Beside the text' },
] as const

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

function formatMegabytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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
  const [file, setFile] = useState<File | null>(null)
  const [images, setImages] = useState<File[]>([])
  const [neededImages, setNeededImages] = useState<string[]>([])
  const [imageNotice, setImageNotice] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const pickedFileRef = useRef<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const isClass = home.kind === 'lesson' || home.kind === 'lessons'
  const selectedLessonId = home.kind === 'lesson'
    ? lessons.find((lesson) => lesson.id === home.lessonId)?.id ?? lessons[0]?.id ?? ''
    : ''
  const isJson = file !== null && file.name.toLowerCase().endsWith('.json')
  const files = file ? [file, ...(isJson ? images : [])] : []
  const status = imageStatus(isJson ? neededImages : [], isJson ? images : [])
  const totalBytes = files.reduce((sum, item) => sum + item.size, 0)
  const tooLarge = totalBytes > MAX_REQUEST_BYTES
  const homeReady = home.kind === 'book'
    ? home.sourceId.length > 0
    : home.kind === 'lessons' || selectedLessonId.length > 0
  const hasContent = isClass ? files.length > 0 : files.length > 0 || notes.trim().length > 0
  const ready = homeReady && hasContent && status.missing.length === 0 && !tooLarge

  const pickFile = (next: File | null) => {
    pickedFileRef.current = next
    setFile(next)
    setNeededImages([])
    if (!next) return
    setNotes('')
    if (!next.name.toLowerCase().endsWith('.json')) return
    next
      .text()
      .then((text) => {
        if (pickedFileRef.current === next) setNeededImages(questionImageNames(text))
      })
      .catch(() => undefined)
  }

  const clearUploads = () => {
    pickFile(null)
    setImages([])
    setImageNotice(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (imageInputRef.current) imageInputRef.current.value = ''
  }

  const addImages = (picked: File[]) => {
    const { files: next, dropped } = mergeImages(images, picked)
    setImages(next)
    setImageNotice(dropped > 0 ? `Only ${MAX_QUESTION_IMAGES} images fit. ${dropped} not added.` : null)
    if (imageInputRef.current) imageInputRef.current.value = ''
  }
  const homeName = home.kind === 'book'
    ? sourceTitleFor(readySources.find((source) => source.id === home.sourceId))
    : home.kind === 'lessons'
      ? 'Classes'
      : lessons.find((lesson) => lesson.id === selectedLessonId)?.title ?? ''

  const submit = async () => {
    if (!ready || !activeWorkspace) return
    const nextHome: KnowledgeHome = home.kind === 'lesson'
      ? { kind: 'lesson', lessonId: selectedLessonId }
      : home
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
      setError(errorMessage(caught, isClass ? 'Could not save this upload.' : 'Could not start structuring.'))
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
            {isSubmitting ? 'Starting…' : isClass ? 'Save' : 'Start structure'}
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
                clearUploads()
                setNotes('')
              }}
            >
              Book
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isClass}
              className={isClass ? 'is-active' : undefined}
              onClick={() => {
                if (isClass) return
                setHome({ kind: 'lesson', lessonId: lessons[0]?.id ?? '' })
                clearUploads()
                setNotes('')
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
                value={home.kind === 'lessons' ? EVERY_CLASS : selectedLessonId}
                onChange={(event) => {
                  const value = event.target.value
                  setHome(value === EVERY_CLASS ? { kind: 'lessons' } : { kind: 'lesson', lessonId: value })
                }}
              >
                <option value={EVERY_CLASS}>Every class named in the file</option>
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
                {home.kind === 'lessons'
                  ? "Each question's term must be the class title."
                  : 'A study guide or a question pack for this class. Terms, lists, abbreviations, compares, and ELOs in the JSON are written into the wiki. Question images can be added beside the file, or zipped with it.'}
              </p>
            </>
          )}
        </div>
        <div className="kproj-field">
          <label className="kproj-label" htmlFor="kproj-file">
            {isClass ? 'JSON Data Upload' : 'Notes file'}
          </label>
          <div className="kproj-file">
            <input
              ref={fileInputRef}
              id="kproj-file"
              type="file"
              hidden
              accept={isClass ? '.json,.zip' : '.json,.md,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.zip'}
              onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
            />
            <button type="button" className="as-console__cta as-console__cta--ghost" onClick={() => fileInputRef.current?.click()}>
              {isClass ? (home.kind === 'lessons' ? '⇪ Upload questions' : '⇪ Upload JSON') : '⇪ Upload notes'}
            </button>
            {file ? <span className="kproj-file__name">{file.name}</span> : null}
            {file ? (
              <button type="button" className="kproj-file__clear" onClick={clearUploads}>
                Clear
              </button>
            ) : null}
          </div>
          <p className="dsn-hint">
            {isClass
              ? home.kind === 'lessons'
                ? "One JSON question pack, or a zip of the JSON and its images. Each question's term must be the class title."
                : 'One JSON file. A study guide becomes wiki entries for this class. A question pack can be a zip of the JSON and its images.'
              : 'JSON with terms, key lists, and ELOs is imported as wiki entries. Other files are transcribed first. A question pack with pictures can be a zip of the JSON and the images.'}
          </p>
        </div>
        {isJson ? (
          <div className="kproj-field">
            <label className="kproj-label" htmlFor="kproj-images">
              Question images
            </label>
            <div className="kproj-file">
              <input
                ref={imageInputRef}
                id="kproj-images"
                type="file"
                hidden
                multiple
                accept={IMAGE_ACCEPT}
                onChange={(event) => addImages(event.target.files ? Array.from(event.target.files) : [])}
              />
              <button
                type="button"
                className="as-console__cta as-console__cta--ghost"
                disabled={images.length >= MAX_QUESTION_IMAGES}
                onClick={() => imageInputRef.current?.click()}
              >
                ⇪ Add images
              </button>
              <span className="kproj-file__name">
                {images.length} of {MAX_QUESTION_IMAGES}
              </span>
              {images.length > 0 ? (
                <button
                  type="button"
                  className="kproj-file__clear"
                  onClick={() => {
                    setImages([])
                    setImageNotice(null)
                  }}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            {images.length > 0 ? (
              <ul className="kproj-images">
                {images.map((image) => (
                  <li key={image.name} className={status.unused.includes(image.name) ? 'is-unused' : undefined}>
                    <span>{image.name}</span>
                    {status.unused.includes(image.name) ? <span className="kproj-images__tag">Not used</span> : null}
                    <button
                      type="button"
                      className="kproj-file__clear"
                      aria-label={`Remove ${image.name}`}
                      onClick={() => setImages(images.filter((item) => item !== image))}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className={`dsn-hint${status.missing.length > 0 ? ' is-error' : ''}`}>
              {neededImages.length === 0
                ? 'No question in this file names an image.'
                : `${status.attached.length} of ${neededImages.length} images attached.`}
              {status.missing.length > 0 ? ` Missing: ${status.missing.join(', ')}.` : ''}
            </p>
            {imageNotice ? <p className="dsn-hint is-error">{imageNotice}</p> : null}
            <p className="dsn-hint">
              Add up to {MAX_QUESTION_IMAGES} PNG, JPEG, or WebP images. Each file name has to match the image filename
              on its question.
            </p>
          </div>
        ) : null}
        {tooLarge ? (
          <p className="dsn-hint is-error">
            This upload is {formatMegabytes(totalBytes)}. The limit is {formatMegabytes(MAX_REQUEST_BYTES)}. Shrink the
            images or split the questions into two packs.
          </p>
        ) : null}
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
  const actionLabel = isBusy ? 'Saving…' : 'Save and finish'

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
                onDone()
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
