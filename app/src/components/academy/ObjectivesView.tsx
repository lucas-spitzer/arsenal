import { Download, ExternalLink, MessagesSquare, Paperclip, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { createThread } from '../../lib/assistantApi'
import {
  fileTypeLabel,
  formatFileSize,
  lessonSeedPrompt,
} from '../../lib/lessonObjectives'
import { lessonResourceUrl, type Lesson, type LessonResource } from '../../lib/lessonsApi'
import { useLessons } from '../../lib/useLessons'
import { Loader } from '../shared/Loader'
import { StudyHead } from './StudySessionChrome'
import { emptyAcademyScope, type AcademyPage, type AcademyScope } from './types'

type ObjectivesViewProps = {
  /** Class to open and scroll to, from an `/app/elo/:lessonId` citation link. */
  focusLessonId?: string | null
  focusResourceId?: string | null
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function Highlight({ text, query }: { text: string; query: string }) {
  const needle = query.trim()
  if (!needle) return <>{text}</>
  const parts = text.split(new RegExp(`(${escapeRegExp(needle)})`, 'ig'))
  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === needle.toLowerCase() ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  )
}

function materialsSummary(resources: LessonResource[]): string | null {
  const files = resources.filter((resource) => resource.kind === 'file').length
  const links = resources.length - files
  const parts = [
    files ? `${files} ${files === 1 ? 'file' : 'files'}` : null,
    links ? `${links} ${links === 1 ? 'link' : 'links'}` : null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

function MaterialsRow({
  lesson,
  highlightedId,
  downloadingId,
  onDownload,
}: {
  lesson: Lesson
  highlightedId: string | null
  downloadingId: string | null
  onDownload: (resource: LessonResource) => void
}) {
  if (lesson.resources.length === 0) {
    return <p className="elo__materials-empty">No materials posted</p>
  }
  return (
    <ul className="elo__materials-list">
      {lesson.resources.map((resource) => {
        const classes = `elo__material${resource.id === highlightedId ? ' is-highlighted' : ''}`
        if (resource.kind === 'link' && resource.url) {
          return (
            <li key={resource.id}>
              <a className={classes} href={resource.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} aria-hidden />
                <span className="elo__material-label">Open on {resource.label}</span>
              </a>
            </li>
          )
        }
        const size = formatFileSize(resource.file_size_bytes)
        return (
          <li key={resource.id}>
            <button
              type="button"
              className={classes}
              onClick={() => onDownload(resource)}
              disabled={downloadingId === resource.id}
              title={`Download ${resource.filename ?? resource.label}`}
            >
              <Download size={14} aria-hidden />
              <span className="elo__material-type">{fileTypeLabel(resource)}</span>
              <span className="elo__material-label">{resource.label}</span>
              {size && <span className="elo__material-size">{size}</span>}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function ObjectivesView({ focusLessonId = null, focusResourceId = null, onOpen }: ObjectivesViewProps) {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const { lessons, error, hasLoaded, isLoading } = useLessons(workspaceId)

  const [query, setQuery] = useState('')
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [discussingId, setDiscussingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const scrolledRef = useRef(false)

  const lesson = useMemo(
    () => (focusLessonId ? lessons.find((item) => item.id === focusLessonId) ?? null : null),
    [focusLessonId, lessons],
  )
  const searching = query.trim().length > 0
  const objectives = useMemo(() => {
    if (!lesson) return []
    const needle = query.trim().toLowerCase()
    if (!needle) return lesson.objectives
    return lesson.objectives.filter(
      (objective) =>
        objective.text.toLowerCase().includes(needle) ||
        (objective.code ?? '').toLowerCase().includes(needle),
    )
  }, [lesson, query])

  useEffect(() => {
    if (!focusLessonId || scrolledRef.current || lessons.length === 0) return
    scrolledRef.current = true
    document.getElementById(`elo-class-${focusLessonId}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [focusLessonId, lessons])

  const download = async (resource: LessonResource) => {
    if (!workspaceId || !lesson) return
    setActionError(null)
    setDownloadingId(resource.id)
    try {
      const url = await lessonResourceUrl(workspaceId, lesson.id, resource.id)
      window.location.assign(url)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not download the file.')
    } finally {
      setDownloadingId(null)
    }
  }

  const discuss = async () => {
    if (!workspaceId || !lesson || discussingId) return
    setActionError(null)
    setDiscussingId(lesson.id)
    try {
      const thread = await createThread(workspaceId, {
        title: lesson.title,
        submode: 'tbs',
        lesson_id: lesson.id,
        seed_prompt: lessonSeedPrompt(lesson),
      })
      onOpen('discussions', { ...emptyAcademyScope, threadId: thread.id })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not start the discussion.')
      setDiscussingId(null)
    }
  }

  const asyncCount = lesson?.objectives.filter((objective) => objective.is_async).length ?? 0
  const summary = lesson ? materialsSummary(lesson.resources) : null
  let body: ReactNode
  if (!hasLoaded && isLoading) {
    body = (
      <div className="lib__empty">
        <Loader label="Loading ELOs" size="sm" />
      </div>
    )
  } else if (error) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">ELOs unavailable</p>
        <p className="lib__empty-copy">{error}</p>
      </div>
    )
  } else if (!lesson) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">{focusLessonId ? 'Class unavailable' : 'Open a class from the Library'}</p>
        <p className="lib__empty-copy">
          {focusLessonId
            ? 'That class is not in this workspace.'
            : 'Each class has an ELO item on its shelf.'}
        </p>
      </div>
    )
  } else {
    body = (
      <div className="elo__classes">
        <article id={`elo-class-${lesson.id}`} className="elo__class is-open is-focused">
          <header className="elo__class-head">
            <div className="elo__class-name">
              <h3 className="elo__class-title">
                <Highlight text={lesson.title} query={query} />
              </h3>
            </div>
            <div className="elo__class-meta">
              <span>
                {lesson.objectives.length} {lesson.objectives.length === 1 ? 'ELO' : 'ELOs'}
              </span>
              {asyncCount > 0 && <span className="elo__async">{asyncCount} async</span>}
              {summary && (
                <span className="elo__class-files">
                  <Paperclip size={12} aria-hidden />
                  {summary}
                </span>
              )}
            </div>
            <button
              type="button"
              className="elo__discuss"
              onClick={() => void discuss()}
              disabled={discussingId !== null}
            >
              <MessagesSquare size={14} aria-hidden />
              {discussingId === lesson.id ? 'Starting…' : 'Discuss this class'}
            </button>
          </header>
          <div className="elo__class-body" id={`elo-class-body-${lesson.id}`}>
            <section className="elo__materials" aria-label={`${lesson.title} materials`}>
              <span className="elo__section-label">Materials</span>
              <MaterialsRow
                lesson={lesson}
                highlightedId={focusResourceId}
                downloadingId={downloadingId}
                onDownload={(resource) => void download(resource)}
              />
            </section>
            {searching && objectives.length < lesson.objectives.length && (
              <p className="elo__filtered">
                Showing {objectives.length} of {lesson.objectives.length} ELOs
              </p>
            )}
            {objectives.length > 0 ? (
              <ol className="elo__list">
                {objectives.map((objective) => (
                  <li key={objective.id} className="elo__item">
                    <span className="elo__num">{objective.position}</span>
                    <p className="elo__text">
                      <Highlight text={objective.text} query={query} />
                    </p>
                    <div className="elo__tags">
                      {objective.code && (
                        <code className="elo__code">
                          <Highlight text={objective.code} query={query} />
                        </code>
                      )}
                      {objective.is_async && <span className="elo__async">Async</span>}
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="elo__materials-empty">
                {searching ? 'No matching ELOs' : 'No ELOs posted for this class.'}
              </p>
            )}
          </div>
        </article>
      </div>
    )
  }

  return (
    <section className="elo study-session" aria-busy={isLoading}>
      <StudyHead
        eyebrow="Enabling learning objectives"
        title={lesson?.title ?? 'ELOs'}
        description="ELOs, lecture slides, and MCeLE material for this class."
        stats={
          lesson
            ? [
                { value: lesson.objectives.length, label: 'ELOs' },
                { value: asyncCount, label: 'async' },
                { value: lesson.resources.length, label: 'materials' },
              ]
            : []
        }
      />

      {lesson ? (
        <div className="elo__toolbar">
          <label className="lib__search elo__search">
            <Search size={15} aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search ELOs or codes"
              aria-label="Search ELOs"
            />
            {searching && (
              <button type="button" className="elo__search-clear" onClick={() => setQuery('')} aria-label="Clear search">
                <X size={14} />
              </button>
            )}
          </label>
          {searching ? (
            <span className="elo__result-count" aria-live="polite">
              {objectives.length} {objectives.length === 1 ? 'ELO' : 'ELOs'}
            </span>
          ) : null}
        </div>
      ) : null}

      {actionError && <p className="chat__error">{actionError}</p>}
      {body}
    </section>
  )
}
