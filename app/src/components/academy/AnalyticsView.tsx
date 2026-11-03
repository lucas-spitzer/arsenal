import { ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { FoundryLoader } from '../foundry/FoundryLoader'
import {
  accuracyPercent,
  resultBatchKey,
  summarizeQuizResults,
  type BatchAccuracy,
  type WeakTerm,
} from '../../lib/quizAnalytics'
import { quizBatchKey } from '../../lib/quizBatches'
import { listQuizResults, type QuizResult } from '../../lib/quizResultsApi'
import { StudyHead } from './StudySessionChrome'
import type { AcademyPage, AcademyScope } from './types'

function formatResultDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function scopeLabel(scope: QuizResult['scope']): string {
  return scope === 'every_variant' ? 'Every variant' : 'One question per term'
}

function figureValue(value: number | null, suffix = ''): string {
  if (value == null) return '—'
  return `${value}${suffix}`
}

export function AnalyticsView({
  onOpen,
}: {
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}) {
  const { activeWorkspace } = useWorkspace()
  const { wikiEntries } = useWorkspaceData()
  const [loaded, setLoaded] = useState<{ workspaceId: string; results: QuizResult[] } | null>(null)
  const [failure, setFailure] = useState<{ workspaceId: string; message: string } | null>(null)
  const [batchKey, setBatchKey] = useState('all')
  const [openId, setOpenId] = useState<string | null>(null)

  const workspaceId = activeWorkspace?.id ?? null
  const results = loaded?.workspaceId === workspaceId ? loaded.results : null
  const error = failure?.workspaceId === workspaceId ? failure.message : null

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    listQuizResults(workspaceId)
      .then((rows) => {
        if (cancelled) return
        setLoaded({ workspaceId, results: rows })
        setFailure(null)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setFailure({
            workspaceId,
            message: caught instanceof Error ? caught.message : 'Could not load analytics.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const wikiLabels = useMemo(
    () => new Map(wikiEntries.map((entry) => [entry.id, entry.preferred_label])),
    [wikiEntries],
  )
  const summary = useMemo(
    () => (results ? summarizeQuizResults(results, { batchKey, wikiLabels }) : null),
    [batchKey, results, wikiLabels],
  )
  const batchOptions = useMemo(() => {
    const seen = new Map<string, string>()
    for (const result of results ?? []) {
      const key = resultBatchKey(result)
      if (!seen.has(key)) seen.set(key, result.title)
    }
    return [...seen.entries()].map(([key, title]) => ({ key, title }))
  }, [results])

  const practice = (term: WeakTerm) => {
    onOpen('quiz', {
      sourceId: term.sourceId,
      targetId: null,
      projectId: term.projectId,
      batchKey: quizBatchKey(term.sourceId, term.projectId),
    })
  }

  let body
  if (error) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">Analytics unavailable</p>
        <p className="lib__empty-copy">{error}</p>
      </div>
    )
  } else if (results == null) {
    body = (
      <div className="lib__empty">
        <FoundryLoader label="Loading analytics" size="sm" />
      </div>
    )
  } else if (results.length === 0) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">No finished quizzes yet</p>
        <p className="lib__empty-copy">Finish a quiz and the score will show up here.</p>
      </div>
    )
  } else if (summary && summary.quizzesTaken === 0) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">No quizzes for this batch</p>
        <p className="lib__empty-copy">Choose All batches, or finish this batch once.</p>
      </div>
    )
  } else if (summary) {
    body = (
      <div className="anl__stack">
        <div className="anl__grid">
          <section>
            <h2 className="anl__label">By batch</h2>
            <div className="anl__rows">
              {summary.batches.map((batch) => (
                <button
                  key={batch.key}
                  type="button"
                  className={`anl__row${batch.key === batchKey ? ' is-open' : ''}`}
                  onClick={() => setBatchKey(batch.key === batchKey ? 'all' : batch.key)}
                >
                  <span className="anl__row-title">{batch.title}</span>
                  <BatchMeta batch={batch} />
                </button>
              ))}
            </div>
          </section>

          <section>
            <h2 className="anl__label">Needs work</h2>
            {summary.needsWork.length === 0 ? (
              <p className="anl__note">Nothing missed in this view.</p>
            ) : (
              <div className="anl__rows">
                {summary.needsWork.map((term) => (
                  <article key={term.key} className="anl__row">
                    <div className="anl__term">
                      <p className="anl__row-title">{term.label}</p>
                      <p className="anl__note">
                        {term.correct} of {term.answered} correct
                      </p>
                    </div>
                    <button type="button" className="anl__practice" onClick={() => practice(term)}>
                      Practice
                    </button>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        <section>
          <h2 className="anl__label">Recent quizzes</h2>
          <div className="anl__rows">
            {summary.recent.map((result) => {
              const misses = result.answers.filter((answer) => !answer.correct)
              const open = openId === result.id
              return (
                <article key={result.id} className={`anl__row anl__row--run${open ? ' is-open' : ''}`}>
                  <button
                    type="button"
                    className="anl__run-toggle"
                    aria-expanded={open}
                    onClick={() => setOpenId(open ? null : result.id)}
                  >
                    <ChevronRight className="anl__chev" size={16} aria-hidden />
                    <span className="anl__row-title">{result.title}</span>
                    <span className="anl__row-meta">
                      <span>{formatResultDate(result.completed_at)}</span>
                      <span>
                        {result.correct_count} of {result.question_count}
                      </span>
                      <span>{scopeLabel(result.scope)}</span>
                    </span>
                  </button>
                  {open ? (
                    misses.length > 0 ? (
                      <ul className="anl__misses">
                        {misses.map((miss) => (
                          <li key={miss.quiz_id}>
                            <p>{miss.question}</p>
                            <p>
                              You picked {miss.selected}. The answer is {miss.answer}.
                            </p>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="anl__note anl__run-clear">Every question was correct.</p>
                    )
                  ) : null}
                </article>
              )
            })}
          </div>
        </section>
      </div>
    )
  }

  return (
    <section className="anl study-session" aria-busy={results == null && !error}>
      <StudyHead
        eyebrow="Quiz results"
        title="Analytics"
        description="Your quizzes and the questions you have answered."
        stats={[
          { value: summary ? figureValue(summary.accuracy, '%') : '—', label: 'accuracy' },
          { value: summary?.questionsAnswered ?? '—', label: 'questions' },
          { value: summary?.quizzesTaken ?? '—', label: 'quizzes' },
        ]}
      />

      {results && results.length > 0 ? (
        <div className="anl__toolbar">
          <label className="lib__select">
            <span className="lib__select-label">Batch</span>
            <select
              value={batchOptions.some((option) => option.key === batchKey) ? batchKey : 'all'}
              onChange={(event) => {
                setBatchKey(event.target.value)
                setOpenId(null)
              }}
              aria-label="Analytics batch"
            >
              <option value="all">All batches</option>
              {batchOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.title}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}

      {body}
    </section>
  )
}

function BatchMeta({ batch }: { batch: BatchAccuracy }) {
  const accuracy = accuracyPercent(batch.correct, batch.questionsAnswered)
  return (
    <span className="anl__batch-meta">
      {batch.quizzesTaken} {batch.quizzesTaken === 1 ? 'quiz' : 'quizzes'}
      {' · '}
      {figureValue(accuracy, '%')}
    </span>
  )
}
