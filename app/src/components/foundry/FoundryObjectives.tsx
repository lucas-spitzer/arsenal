import { ExternalLink, Pencil, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  fileTypeLabel,
  formatFileSize,
  indexStatusLabel,
  LESSON_FILE_ACCEPT,
  lessonStats,
  objectivesToText,
  parseObjectiveLines,
} from '../../lib/lessonObjectives'
import {
  addLessonLink,
  createLesson,
  deleteLesson,
  deleteLessonResource,
  reindexAllLessons,
  reindexLessonResource,
  replaceLessonObjectives,
  updateLesson,
  uploadLessonFiles,
  type Lesson,
  type LessonResource,
} from '../../lib/lessonsApi'
import { useLessons } from '../../lib/useLessons'
import { ErrorBanner } from './ErrorBanner'
import { FoundryDialog } from './FoundryDialog'
import { FoundryLoader } from './FoundryLoader'

const POLL_MS = 5000

type LessonDraft = {
  title: string
  sort_order: string
  notes: string
  objectives: string
}

type EditorState = { mode: 'closed' } | { mode: 'create' } | { mode: 'edit'; lesson: Lesson }

type PendingDelete =
  | { kind: 'lesson'; lesson: Lesson }
  | { kind: 'resource'; lesson: Lesson; resource: LessonResource }

function draftFromLesson(lesson: Lesson): LessonDraft {
  return {
    title: lesson.title,
    sort_order: String(lesson.sort_order),
    notes: lesson.notes ?? '',
    objectives: objectivesToText(lesson.objectives),
  }
}

function emptyDraft(nextOrder: number): LessonDraft {
  return { title: '', sort_order: String(nextOrder), notes: '', objectives: '' }
}

function statusClass(resource: LessonResource): string {
  if (resource.kind === 'link' || resource.index_status === 'skipped') return 'is-muted'
  if (resource.index_status === 'ready') return 'is-ready'
  if (resource.index_status === 'failed') return 'is-failed'
  return 'is-pending'
}

function LinkForm({
  disabled,
  onSubmit,
}: {
  disabled: boolean
  onSubmit: (label: string, url: string) => Promise<boolean>
}) {
  const [label, setLabel] = useState('MarineNet')
  const [url, setUrl] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!url.trim()) return
    if (await onSubmit(label.trim() || 'MarineNet', url.trim())) setUrl('')
  }

  return (
    <form className="as-console__elo-link-form" onSubmit={(event) => void submit(event)}>
      <input
        className="as-wiki__input"
        value={label}
        onChange={(event) => setLabel(event.target.value)}
        aria-label="Link label"
        placeholder="MarineNet"
        disabled={disabled}
      />
      <input
        className="as-wiki__input"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        aria-label="Link URL"
        placeholder="https://elearning.mcele.usmc.mil/…"
        type="url"
        disabled={disabled}
      />
      <button type="submit" className="as-console__cta as-console__cta--ghost" disabled={disabled || !url.trim()}>
        Add link
      </button>
    </form>
  )
}

export function FoundryObjectives() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const { lessons, error, hasLoaded, isLoading, reload } = useLessons(workspaceId)

  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' })
  const [draft, setDraft] = useState<LessonDraft>(() => emptyDraft(1))
  const [formError, setFormError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const [busyLessonId, setBusyLessonId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const fileInputs = useRef(new Map<string, HTMLInputElement>())

  const stats = useMemo(() => lessonStats(lessons), [lessons])
  const parsedObjectives = useMemo(() => parseObjectiveLines(draft.objectives), [draft.objectives])
  const isIndexing = lessons.some((lesson) =>
    lesson.resources.some((resource) => resource.index_status === 'pending' || resource.index_status === 'indexing'),
  )

  useEffect(() => {
    if (!isIndexing) return
    const timer = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(timer)
  }, [isIndexing, reload])

  const openCreate = () => {
    const nextOrder = lessons.reduce((max, lesson) => Math.max(max, lesson.sort_order), 0) + 1
    setDraft(emptyDraft(nextOrder))
    setFormError(null)
    setEditor({ mode: 'create' })
  }

  const openEdit = (lesson: Lesson) => {
    setDraft(draftFromLesson(lesson))
    setFormError(null)
    setEditor({ mode: 'edit', lesson })
  }

  const closeEditor = () => {
    if (!isSaving) setEditor({ mode: 'closed' })
  }

  const update = <K extends keyof LessonDraft>(key: K, value: LessonDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  const handleSave = async () => {
    if (!workspaceId || isSaving || editor.mode === 'closed') return
    const title = draft.title.trim()
    if (!title) {
      setFormError('Enter the class title.')
      return
    }
    const sortOrder = Number.parseInt(draft.sort_order, 10)
    const fields = {
      title,
      sort_order: Number.isFinite(sortOrder) ? sortOrder : null,
      notes: draft.notes.trim() || null,
    }
    setIsSaving(true)
    setFormError(null)
    try {
      if (editor.mode === 'create') {
        await createLesson(workspaceId, { ...fields, objectives: parsedObjectives })
      } else {
        const { lesson } = editor
        const changed =
          fields.title !== lesson.title ||
          fields.notes !== (lesson.notes ?? null) ||
          (fields.sort_order !== null && fields.sort_order !== lesson.sort_order)
        if (changed) await updateLesson(workspaceId, lesson.id, fields)
        if (draft.objectives.trim() !== objectivesToText(lesson.objectives).trim()) {
          await replaceLessonObjectives(workspaceId, lesson.id, parsedObjectives)
        }
      }
      setEditor({ mode: 'closed' })
      reload()
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : 'Could not save this class.')
    } finally {
      setIsSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!workspaceId || !pendingDelete || isDeleting) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      if (pendingDelete.kind === 'lesson') {
        await deleteLesson(workspaceId, pendingDelete.lesson.id)
      } else {
        await deleteLessonResource(workspaceId, pendingDelete.lesson.id, pendingDelete.resource.id)
      }
      setPendingDelete(null)
      reload()
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : 'Could not delete.')
    } finally {
      setIsDeleting(false)
    }
  }

  const runLessonAction = async (lessonId: string, action: () => Promise<unknown>, failure: string) => {
    if (!workspaceId) return false
    setBusyLessonId(lessonId)
    setActionError(null)
    setNotice(null)
    try {
      await action()
      reload()
      return true
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : failure)
      return false
    } finally {
      setBusyLessonId(null)
    }
  }

  const upload = (lesson: Lesson, files: FileList | null) => {
    if (!workspaceId || !files || files.length === 0) return
    const chosen = Array.from(files)
    void runLessonAction(
      lesson.id,
      () => uploadLessonFiles(workspaceId, lesson.id, chosen),
      'Could not upload the files.',
    )
  }

  const reindexAll = async () => {
    if (!workspaceId) return
    setActionError(null)
    setNotice(null)
    try {
      const result = await reindexAllLessons(workspaceId)
      setNotice(`Queued ELOs for ${result.lessons} classes and ${result.files} files for Discussions search.`)
      reload()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Could not queue re-indexing.')
    }
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Academics</div>
          <h2>ELOs</h2>
        </div>
        <span className="as-console__live">
          {stats.classes} classes · {stats.elos} ELOs{isIndexing ? ' · indexing' : ''}
        </span>
        <button
          type="button"
          className="as-console__cta as-console__cta--ghost"
          onClick={() => void reindexAll()}
          disabled={!workspaceId || lessons.length === 0}
          title="Rebuild the Discussions search index for every ELO and lesson file"
        >
          Re-index all
        </button>
        <button type="button" className="as-console__cta" onClick={openCreate} disabled={!workspaceId}>
          + New class
        </button>
      </header>

      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}
        {actionError ? <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} /> : null}
        {notice ? <p className="as-console__elo-notice">{notice}</p> : null}
        <p className="as-console__elo-hint">
          Published to Academy ELO. Uploaded PDF, PPTX, DOCX, and TXT files are searched by Discussions.
        </p>

        {!hasLoaded && isLoading ? (
          <section className="as-console__panel">
            <div className="as-console__empty">
              <FoundryLoader label="Loading ELOs" size="sm" />
            </div>
          </section>
        ) : lessons.length === 0 ? (
          <section className="as-console__panel">
            <div className="as-console__empty">No classes yet. Add a class and paste its ELOs.</div>
          </section>
        ) : (
          <div className="as-console__elo-classes">
            {lessons.map((lesson) => {
              const busy = busyLessonId === lesson.id
              return (
                <section key={lesson.id} className="as-console__panel as-console__elo-class">
                  <div className="as-console__elo-head">
                    <span className="as-console__elo-order">{String(lesson.sort_order).padStart(2, '0')}</span>
                    <h3 className="as-console__elo-title">{lesson.title}</h3>
                    <span className="as-console__elo-count">
                      {lesson.objectives.length} {lesson.objectives.length === 1 ? 'ELO' : 'ELOs'}
                    </span>
                    <button
                      type="button"
                      className="as-console__cal-icon"
                      onClick={() => openEdit(lesson)}
                      aria-label={`Edit ${lesson.title}`}
                      title="Edit class and ELOs"
                    >
                      <Pencil size={14} aria-hidden />
                    </button>
                    <button
                      type="button"
                      className="as-console__cal-icon as-console__cal-icon--danger"
                      onClick={() => {
                        setDeleteError(null)
                        setPendingDelete({ kind: 'lesson', lesson })
                      }}
                      aria-label={`Delete ${lesson.title}`}
                      title="Delete class"
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>

                  {lesson.objectives.length > 0 && (
                    <details className="as-console__elo-objectives">
                      <summary>Show ELOs</summary>
                      <ol>
                        {lesson.objectives.map((objective) => (
                          <li key={objective.id}>
                            {objective.text}
                            {objective.is_async ? <span className="as-console__elo-tag">Async</span> : null}
                            {objective.code ? <code>{objective.code}</code> : null}
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}

                  <div className="as-console__elo-materials">
                    {lesson.resources.length === 0 ? (
                      <p className="as-console__elo-none">No materials yet.</p>
                    ) : (
                      <ul>
                        {lesson.resources.map((resource) => {
                          const size = formatFileSize(resource.file_size_bytes)
                          const canReindex =
                            resource.kind === 'file' && resource.index_status !== 'skipped'
                          return (
                            <li key={resource.id} className="as-console__elo-resource">
                              <span className="as-console__elo-type">{fileTypeLabel(resource)}</span>
                              {resource.kind === 'link' && resource.url ? (
                                <a
                                  className="as-console__elo-label"
                                  href={resource.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={resource.url}
                                >
                                  {resource.label} <ExternalLink size={12} aria-hidden />
                                </a>
                              ) : (
                                <span className="as-console__elo-label" title={resource.filename ?? undefined}>
                                  {resource.label}
                                </span>
                              )}
                              {size ? <span className="as-console__elo-size">{size}</span> : null}
                              <span
                                className={`as-console__elo-status ${statusClass(resource)}`}
                                title={resource.index_error ?? undefined}
                              >
                                {indexStatusLabel(resource)}
                              </span>
                              {canReindex ? (
                                <button
                                  type="button"
                                  className="as-console__cal-icon"
                                  onClick={() =>
                                    void runLessonAction(
                                      lesson.id,
                                      () => reindexLessonResource(workspaceId ?? '', lesson.id, resource.id),
                                      'Could not queue re-indexing.',
                                    )
                                  }
                                  disabled={busy}
                                  aria-label={`Re-index ${resource.label}`}
                                  title="Re-index for Discussions"
                                >
                                  <RefreshCw size={14} aria-hidden />
                                </button>
                              ) : null}
                              <button
                                type="button"
                                className="as-console__cal-icon as-console__cal-icon--danger"
                                onClick={() => {
                                  setDeleteError(null)
                                  setPendingDelete({ kind: 'resource', lesson, resource })
                                }}
                                aria-label={`Remove ${resource.label}`}
                                title="Remove"
                              >
                                <Trash2 size={14} aria-hidden />
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    )}

                    <div className="as-console__elo-add">
                      <input
                        ref={(node) => {
                          if (node) fileInputs.current.set(lesson.id, node)
                          else fileInputs.current.delete(lesson.id)
                        }}
                        type="file"
                        multiple
                        accept={LESSON_FILE_ACCEPT}
                        hidden
                        onChange={(event) => {
                          upload(lesson, event.target.files)
                          event.target.value = ''
                        }}
                      />
                      <button
                        type="button"
                        className="as-console__cta as-console__cta--ghost"
                        onClick={() => fileInputs.current.get(lesson.id)?.click()}
                        disabled={busy}
                      >
                        <Upload size={14} aria-hidden /> {busy ? 'Working…' : 'Upload files'}
                      </button>
                      <LinkForm
                        disabled={busy}
                        onSubmit={(label, url) =>
                          runLessonAction(
                            lesson.id,
                            () => addLessonLink(workspaceId ?? '', lesson.id, { label, url }),
                            'Could not add the link.',
                          )
                        }
                      />
                    </div>
                  </div>
                </section>
              )
            })}
          </div>
        )}
      </div>

      <FoundryDialog
        title={editor.mode === 'edit' ? 'Edit class' : 'New class'}
        open={editor.mode !== 'closed'}
        onClose={closeEditor}
      >
        <form
          className="as-console__dialog-form"
          onSubmit={(submit) => {
            submit.preventDefault()
            void handleSave()
          }}
        >
          {formError ? <ErrorBanner message={formError} /> : null}

          <div className="as-console__cal-fields as-console__elo-fields">
            <div>
              <label className="as-console__field-label" htmlFor="elo-title">
                Class title
              </label>
              <input
                id="elo-title"
                className="as-wiki__input"
                value={draft.title}
                onChange={(change) => update('title', change.target.value)}
                placeholder="Tactical Combat Casualty Care"
                autoFocus
                disabled={isSaving}
              />
            </div>
            <div>
              <label className="as-console__field-label" htmlFor="elo-order">
                Order
              </label>
              <input
                id="elo-order"
                type="number"
                min={0}
                className="as-wiki__input"
                value={draft.sort_order}
                onChange={(change) => update('sort_order', change.target.value)}
                disabled={isSaving}
              />
            </div>
          </div>

          <label className="as-console__field-label" htmlFor="elo-objectives">
            ELOs <span className="as-console__cal-optional">one per line</span>
          </label>
          <textarea
            id="elo-objectives"
            className="as-wiki__textarea as-console__elo-textarea"
            rows={10}
            value={draft.objectives}
            onChange={(change) => update('objectives', change.target.value)}
            placeholder={'1. Without the aid of references, identify the steps of the OODA Cycle without omission. [Async] (MCS-CMBH-1002a)'}
            disabled={isSaving}
          />
          <p className="as-console__elo-hint">
            Paste the list as written. Numbers, [Async], and the trailing (MCS-…) code are read automatically.
          </p>

          {parsedObjectives.length > 0 && (
            <ol className="as-console__elo-preview" aria-label="ELO preview">
              {parsedObjectives.map((objective, index) => (
                <li key={index}>
                  {objective.text}
                  {objective.is_async ? <span className="as-console__elo-tag">Async</span> : null}
                  {objective.code ? <code>{objective.code}</code> : <em> no code</em>}
                </li>
              ))}
            </ol>
          )}

          <label className="as-console__field-label" htmlFor="elo-notes">
            Notes <span className="as-console__cal-optional">optional</span>
          </label>
          <textarea
            id="elo-notes"
            className="as-wiki__textarea"
            rows={2}
            value={draft.notes}
            onChange={(change) => update('notes', change.target.value)}
            disabled={isSaving}
          />

          <div className="as-console__dialog-actions">
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              onClick={closeEditor}
              disabled={isSaving}
            >
              Cancel
            </button>
            <button type="submit" className="as-console__cta" disabled={isSaving}>
              {isSaving
                ? 'Saving…'
                : editor.mode === 'edit'
                  ? 'Save changes'
                  : `Add class (${parsedObjectives.length} ${parsedObjectives.length === 1 ? 'ELO' : 'ELOs'})`}
            </button>
          </div>
        </form>
      </FoundryDialog>

      <FoundryDialog
        title={pendingDelete?.kind === 'resource' ? 'Remove material' : 'Delete class'}
        open={pendingDelete !== null}
        onClose={() => {
          if (!isDeleting) setPendingDelete(null)
        }}
      >
        {deleteError ? <ErrorBanner message={deleteError} /> : null}
        <p className="as-console__confirm-copy">
          {pendingDelete?.kind === 'resource'
            ? `Remove "${pendingDelete.resource.label}" from ${pendingDelete.lesson.title}? Students can no longer download it, and Discussions stops citing it.`
            : pendingDelete
              ? `Delete "${pendingDelete.lesson.title}" with its ELOs and every uploaded file? This cannot be undone.`
              : null}
        </p>
        <div className="as-console__dialog-actions">
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            onClick={() => setPendingDelete(null)}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button type="button" className="as-console__cta" onClick={() => void confirmDelete()} disabled={isDeleting}>
            {isDeleting ? 'Deleting…' : pendingDelete?.kind === 'resource' ? 'Remove' : 'Delete class'}
          </button>
        </div>
      </FoundryDialog>
    </>
  )
}
