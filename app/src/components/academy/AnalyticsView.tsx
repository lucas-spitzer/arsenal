import { useEffect, useState } from 'react'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  getDashboard,
  getLeaderboard,
  type Dashboard,
  type DashboardWeakQuestion,
  type LeaderboardEntry,
  type SubjectKind,
} from '../../lib/atlasApi'
import { Loader } from '../shared/Loader'
import { StudyHead } from './StudySessionChrome'
import { WeakQuestionPractice } from './WeakQuestionPractice'

const ALL_SUBJECTS = 'all'
const PLATOON = 'platoon'

function parseSubject(value: string): { kind: SubjectKind; id: string } | null {
  const [kind, id] = value.split(':')
  if ((kind === 'source' || kind === 'lesson') && id) return { kind, id }
  return null
}

function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    return 'UTC'
  }
}

export function AnalyticsView() {
  const { activeWorkspace } = useWorkspace()
  const { quizzes } = useWorkspaceData()
  const { approvedUser } = useAuth()
  const isAdmin = isAdminAccess(approvedUser?.role)
  const workspaceId = activeWorkspace?.id ?? null

  const [studentId, setStudentId] = useState('')
  const [subject, setSubject] = useState(ALL_SUBJECTS)
  const [roster, setRoster] = useState<LeaderboardEntry[]>([])
  const [loaded, setLoaded] = useState<{ key: string; dashboard: Dashboard } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const [practicing, setPracticing] = useState<DashboardWeakQuestion | null>(null)
  const [reload, setReload] = useState(0)

  const requestKey = `${workspaceId ?? ''}|${studentId}|${subject}`
  const dashboard = loaded?.key === requestKey ? loaded.dashboard : null
  const error = failure?.key === requestKey ? failure.message : null

  useEffect(() => {
    if (!workspaceId || !isAdmin) return
    let cancelled = false
    getLeaderboard(workspaceId)
      .then((board) => {
        if (!cancelled) setRoster(board.entries)
      })
      .catch(() => {
        if (!cancelled) setRoster([])
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, isAdmin])

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    const key = `${workspaceId}|${studentId}|${subject}`
    const picked = parseSubject(subject)
    getDashboard(workspaceId, {
      userId: studentId || null,
      subjectKind: picked?.kind ?? null,
      subjectId: picked?.id ?? null,
      tz: localTimeZone(),
    })
      .then((next) => {
        if (!cancelled) {
          setLoaded({ key, dashboard: next })
          setFailure(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setFailure({ key, message: caught instanceof Error ? caught.message : 'Could not load analytics.' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, studentId, subject, reload])

  const mine = studentId === ''
  const practiceQuiz = practicing ? quizzes.find((quiz) => quiz.id === practicing.quiz_id) ?? null : null

  const openPractice = (row: DashboardWeakQuestion) => {
    if (!mine) return
    setPracticing(row)
  }

  const closePractice = () => {
    setPracticing(null)
    setReload((value) => value + 1)
  }

  let body
  if (error) {
    body = (
      <div className="lib__empty">
        <p className="lib__empty-title">Analytics unavailable</p>
        <p className="lib__empty-copy">{error}</p>
      </div>
    )
  } else if (!dashboard) {
    body = (
      <div className="lib__empty">
        <Loader label="Loading analytics" size="sm" />
      </div>
    )
  } else {
    const { summary } = dashboard
    body = (
      <div className="anl__stack">
        <div className="ldr__platoon">
          <div>
            <span>Atlas Points</span>
            <strong>{summary.lifetime_ap}</strong>
          </div>
          <div>
            <span>Mastered</span>
            <strong>
              {summary.concepts_mastered}
              <small className="anl__of"> of {summary.total_questions}</small>
            </strong>
          </div>
          <div>
            <span>Accuracy</span>
            <strong>{summary.accuracy == null ? '—' : `${summary.accuracy}%`}</strong>
          </div>
          <div>
            <span>Answered</span>
            <strong>{summary.questions_answered}</strong>
          </div>
        </div>

        {mine && practicing ? (
          <WeakQuestionPractice
            key={practicing.quiz_id}
            quiz={practiceQuiz}
            stem={practicing.question}
            subjectName={practicing.subject_name}
            onBack={closePractice}
          />
        ) : (
          <section>
            <h2 className="anl__label">Areas for Improvement</h2>
            {dashboard.weak_questions.length > 0 ? (
              <div className="anl__rows">
                {dashboard.weak_questions.map((row) => (
                  <article key={row.quiz_id} className="anl__row">
                    <div className="anl__term">
                      <p className="anl__row-title">{row.question}</p>
                      <p className="anl__note">
                        {row.subject_name} · {row.correct_count} correct, {row.incorrect_count} missed
                        {studentId === PLATOON ? ' across the platoon' : ''}
                      </p>
                    </div>
                    {mine ? (
                      <button type="button" className="anl__practice" onClick={() => openPractice(row)}>
                        Practice
                      </button>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <p className="anl__note">No missed questions waiting on mastery.</p>
            )}
          </section>
        )}
      </div>
    )
  }

  const subjects = loaded?.dashboard.subjects ?? []

  return (
    <section className="anl study-session" aria-busy={!dashboard && !error}>
      <StudyHead
        eyebrow="Atlas Points"
        title="Analytics"
        description="Points, mastery, and accuracy by subject, with the questions that need work."
      />

      <div className="anl__toolbar">
        {isAdmin ? (
          <label className="lib__select">
            <span className="lib__select-label">Student</span>
            <select
              value={studentId}
              onChange={(event) => {
                setStudentId(event.target.value)
                setSubject(ALL_SUBJECTS)
                setPracticing(null)
              }}
            >
              <option value="">Me</option>
              <option value={PLATOON}>Whole platoon</option>
              {roster
                .filter((entry) => !entry.user_id.startsWith('email:'))
                .map((entry) => (
                  <option key={entry.user_id} value={entry.user_id}>
                    {entry.name}
                  </option>
                ))}
            </select>
          </label>
        ) : null}
        <label className="lib__select">
          <span className="lib__select-label">Subject</span>
          <select
            value={subject}
            onChange={(event) => {
              setSubject(event.target.value)
              setPracticing(null)
            }}
          >
            <option value={ALL_SUBJECTS}>All subjects</option>
            {subjects.map((row) => (
              <option key={`${row.subject_kind}:${row.subject_id}`} value={`${row.subject_kind}:${row.subject_id}`}>
                {row.subject_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {body}
    </section>
  )
}