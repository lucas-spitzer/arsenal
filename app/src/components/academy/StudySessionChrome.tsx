import { ArrowLeft, ArrowRight, BookOpen, ChevronRight, Maximize2, Minimize2, Target } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Lesson } from '../../lib/lessonsApi'

/* Shared chrome for the live study views (Flashcards, Quiz, Scenarios,
   Discussions): roster-style page header, a focusable session panel with
   fullscreen support, an item pager, and a source reference block. */

export function StudyHead({
  eyebrow,
  title,
  description,
  stats,
  children,
}: {
  eyebrow: string
  title: string
  description: string
  stats?: { value: string | number; label: string }[]
  children?: ReactNode
}) {
  return (
    <header className="study-session__head">
      <div className="study-session__ident">
        <p className="study-session__eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="study-session__head-side">
        {children}
        {stats && stats.length > 0 && (
          <div className="study-session__summary" aria-label="Study set summary">
            {stats.map((stat) => (
              <span key={stat.label}>
                <strong>{stat.value}</strong> {stat.label}
              </span>
            ))}
          </div>
        )}
      </div>
    </header>
  )
}

export function StudyPanel({
  fullscreen,
  onToggleFullscreen,
  meta,
  progress,
  center,
  pager,
  children,
}: {
  fullscreen: boolean
  onToggleFullscreen: () => void
  meta?: ReactNode
  progress?: { current: number; total: number } | null
  center?: ReactNode
  pager?: {
    onPrev: () => void
    onNext: () => void
    prevDisabled?: boolean
    nextDisabled?: boolean
    label?: string
  } | null
  children: ReactNode
}) {
  return (
    <div className={`study-session__panel${fullscreen ? ' study-session__panel--fullscreen' : ''}`}>
      <div className="study-session__panel-bar">
        <div className="study-session__panel-meta">{meta}</div>
        <div className="study-session__panel-center">
          {progress && progress.total > 0 ? (
            <div className="study-session__progress" aria-label="Session progress">
              <strong>
                {String(progress.current).padStart(2, '0')}
                <em> / {String(progress.total).padStart(2, '0')}</em>
              </strong>
              <div
                className="study-session__meter"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={progress.total}
                aria-valuenow={progress.current}
              >
                <div style={{ width: `${(progress.current / progress.total) * 100}%` }} />
              </div>
            </div>
          ) : (
            center
          )}
        </div>
        <button
          type="button"
          className="study-session__fullscreen"
          onClick={onToggleFullscreen}
          aria-pressed={fullscreen}
          aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          title={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
        >
          {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>

      <div className="study-session__panel-body">{children}</div>

      {pager && (
        <nav className="study-session__pager" aria-label="Move through the study set">
          <button type="button" disabled={pager.prevDisabled} onClick={pager.onPrev}>
            <ArrowLeft size={16} /> Previous item
          </button>
          {pager.label && <span>{pager.label}</span>}
          <button type="button" disabled={pager.nextDisabled} onClick={pager.onNext}>
            Next item <ArrowRight size={16} />
          </button>
        </nav>
      )}
    </div>
  )
}

export function StudySourceReference({
  sourceId,
  sourceName,
  detail,
}: {
  sourceId: string | null
  sourceName: string
  detail?: string
}) {
  const navigate = useNavigate()
  return (
    <aside className="study-session__reference" aria-label="Source reference">
      <div className="study-session__reference-head">
        <div>
          <span>Source reference</span>
          <strong>{sourceName}</strong>
        </div>
        <BookOpen size={17} aria-hidden />
      </div>
      {detail && <p className="study-session__reference-detail">{detail}</p>}
      <button
        type="button"
        className="study-session__reference-link"
        disabled={!sourceId}
        onClick={() => sourceId && navigate(`/app/reader/${sourceId}`)}
      >
        Open in reader <ChevronRight size={15} />
      </button>
    </aside>
  )
}

export function StudyLessonReference({ lesson }: { lesson: Pick<Lesson, 'id' | 'title' | 'objectives'> }) {
  const navigate = useNavigate()
  const count = lesson.objectives.length
  return (
    <aside className="study-session__reference" aria-label="Class reference">
      <div className="study-session__reference-head">
        <div>
          <span>Class reference</span>
          <strong>{lesson.title}</strong>
        </div>
        <Target size={17} aria-hidden />
      </div>
      <p className="study-session__reference-detail">
        {count} {count === 1 ? 'ELO' : 'ELOs'}. The tutor draws on this class first.
      </p>
      <button
        type="button"
        className="study-session__reference-link"
        onClick={() => navigate(`/app/elo/${lesson.id}`)}
      >
        Open ELOs <ChevronRight size={15} />
      </button>
    </aside>
  )
}
