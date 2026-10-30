import { ChevronRight, Download, ExternalLink, MessagesSquare, Paperclip, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { createThread } from '../../lib/assistantApi'
import {
  fileTypeLabel,
  filterLessons,
  formatFileSize,
  lessonSeedPrompt,
  lessonStats,
} from '../../lib/lessonObjectives'
import { lessonResourceUrl, type Lesson, type LessonResource } from '../../lib/lessonsApi'
import { useLessons } from '../../lib/useLessons'
import { FoundryLoader } from '../foundry/FoundryLoader'
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
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(focusLessonId ? [focusLessonId] : []))
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [discussingId, setDiscussingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const scrolledRef = useRef(false)

  const stats = useMemo(() => lessonStats(lessons), [lessons])
  const matches = useMemo(() => filterLessons(lessons, query), [lessons, query])
  const searching = query.trim().length > 0
  const shownElos = matches.reduce((total, match) => total + match.objectives.length, 0)
  const allOpen = lessons.length > 0 && lessons.every((lesson) => openIds.has(lesson.id))

  useEffect(() => {
    if (!focusLessonId || scrolledRef.current || lessons.length === 0) return
    scrolledRef.current = true
    document.getElementById(`elo-class-${focusLessonId}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [focusLessonId, lessons])

  const toggle = (lessonId: string) => {
    setOpenIds((current) => {
      const next = new Set(current)
      if (next.has(lessonId)) next.delete(lessonId)
      else next.add(lessonId)
      return next
    })
  }

  const toggleAll = () => {
    setOpenIds(allOpen ? new Set() : new Set(lessons.map((lesson) => lesson.id)))
  }

  const download = async (lesson: Lesson, resource: LessonResource) => {
    if (!workspaceId) return
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

  const discuss = async (lesson: Lesson) => {
    if (!workspaceId || discussingId) return
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

  let body: ReactNode
  if (!hasLoaded && isLoading) {
    body = (
      <div className="lib__empty">
        <FoundryLoader label="Loading ELOs" size="sm" />
      </div>
    )
  } else if (error) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">ELOs unavailable</p>
        <p className="lib__empty-copy">{error}</p>
      </div>
    )
  } else if (lessons.length === 0) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">No classes yet</p>
        <p className="lib__empty-copy">The Academics officer posts each class's ELOs and lecture materials here.</p>
      </div>
    )
  } else if (matches.length === 0) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">No matching ELOs</p>
        <p className="lib__empty-copy">Try a class name, an ELO code such as MCS-VALU, or a key term.</p>
      </div>
    )
  } else {
    body = (
      <div className="elo__classes">
        {matches.map(({ lesson, objectives }) => {
          const isOpen = searching || openIds.has(lesson.id)
          const bodyId = `elo-class-body-${lesson.id}`
          const summary = materialsSummary(lesson.resources)
          const asyncCount = lesson.objectives.filter((objective) => objective.is_async).length
          return (
            <article
              key={lesson.id}
              id={`elo-class-${lesson.id}`}
              className={`elo__class${isOpen ? ' is-open' : ''}${lesson.id === focusLessonId ? ' is-focused' : ''}`}
            >
              <header className="elo__class-head">
                <button
                  type="button"
                  className="elo__class-toggle"
                  onClick={() => toggle(lesson.id)}
                  aria-expanded={isOpen}
                  aria-controls={bodyId}
                  disabled={searching}
                >
                  <ChevronRight className="elo__chev" size={16} aria-hidden />
                  <h3 className="elo__class-title">
                    <Highlight text={lesson.title} query={query} />
                  </h3>
                </button>
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
                  onClick={() => void discuss(lesson)}
                  disabled={discussingId !== null}
                >
                  <MessagesSquare size={14} aria-hidden />
                  {discussingId === lesson.id ? 'Starting…' : 'Discuss this class'}
                </button>
              </header>

              {isOpen && (
                <div className="elo__class-body" id={bodyId}>
                  <section className="elo__materials" aria-label={`${lesson.title} materials`}>
                    <span className="elo__section-label">Materials</span>
                    <MaterialsRow
                      lesson={lesson}
                      highlightedId={lesson.id === focusLessonId ? focusResourceId : null}
                      downloadingId={downloadingId}
                      onDownload={(resource) => void download(lesson, resource)}
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
                    <p className="elo__materials-empty">No ELOs posted for this class.</p>
                  )}
                </div>
              )}
            </article>
          )
        })}
      </div>
    )
  }

  return (
    <section className="elo study-session" aria-busy={isLoading}>
      <StudyHead
        eyebrow="Enabling learning objectives"
        title="ELOs"
        description="Every class's ELOs, with the lecture slides and MCeLE material to study them."
        stats={[
          { value: stats.classes, label: 'classes' },
          { value: stats.elos, label: 'ELOs' },
          { value: stats.async, label: 'async' },
        ]}
      />

      <div className="elo__toolbar">
        <label className="lib__search elo__search">
          <Search size={15} aria-hidden />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search ELOs, codes, or classes"
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
            {shownElos} {shownElos === 1 ? 'ELO' : 'ELOs'} in {matches.length}{' '}
            {matches.length === 1 ? 'class' : 'classes'}
          </span>
        ) : (
          <button type="button" className="elo__expand" onClick={toggleAll} disabled={lessons.length === 0}>
            {allOpen ? 'Collapse all' : 'Expand all'}
          </button>
        )}
      </div>

      {actionError && <p className="chat__error">{actionError}</p>}
      {body}
    </section>
  )
}
