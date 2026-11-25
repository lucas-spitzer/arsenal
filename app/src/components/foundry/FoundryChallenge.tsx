import { useCallback, useEffect, useState } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  finalizeCompetition,
  getCompetition,
  getPlatoonDashboard,
  updateCompetition,
  type CompetitionSettings,
  type PlatoonDashboard,
} from '../../lib/atlasApi'
import { StandingsTable } from '../academy/StandingsTable'
import { Loader } from '../shared/Loader'

export function FoundryChallenge() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const [competition, setCompetition] = useState<CompetitionSettings | null>(null)
  const [dashboard, setDashboard] = useState<PlatoonDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [goalDraft, setGoalDraft] = useState('')
  const [loadToken, setLoadToken] = useState(0)

  const reload = useCallback(() => {
    setLoadToken((value) => value + 1)
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    void Promise.all([getCompetition(workspaceId), getPlatoonDashboard(workspaceId)])
      .then(([nextCompetition, nextDashboard]) => {
        if (cancelled) return
        setCompetition(nextCompetition)
        setDashboard(nextDashboard)
        setGoalDraft(nextCompetition.platoon_goal != null ? String(nextCompetition.platoon_goal) : '')
        setError(null)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Could not load the challenge console.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, loadToken])

  if (!workspaceId) return null

  const saveAccess = async (studentAccess: boolean) => {
    setSaving(true)
    try {
      const next = await updateCompetition(workspaceId, { student_access: studentAccess })
      setCompetition(next)
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update access.')
    } finally {
      setSaving(false)
    }
  }

  const saveGoal = async () => {
    setSaving(true)
    try {
      const trimmed = goalDraft.trim()
      const next = await updateCompetition(workspaceId, {
        platoon_goal: trimmed ? Number(trimmed) : null,
      })
      setCompetition(next)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update the platoon goal.')
    } finally {
      setSaving(false)
    }
  }

  const freeze = async () => {
    if (!window.confirm('Freeze final standings now? This snapshots the current leaderboard.')) return
    setSaving(true)
    try {
      const next = await finalizeCompetition(workspaceId)
      setCompetition(next)
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not finalize the competition.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="as-console__panel">
      <header className="as-console__panel-head">
        <div>
          <p className="as-console__eyebrow">Atlas Points</p>
          <h1 className="as-console__title">Challenge</h1>
          <p className="as-console__lede">
            Competition window, student access, and platoon totals. Academy challenge tabs stay admin-only until you open access.
          </p>
        </div>
      </header>

      {error ? <p className="as-console__error">{error}</p> : null}
      {!competition || !dashboard ? (
        <Loader label="Loading challenge" size="sm" />
      ) : (
        <div className="as-console__stack" style={{ display: 'grid', gap: 24 }}>
          <section className="as-console__card" style={{ padding: 20 }}>
            <h2 className="as-console__card-title">Competition</h2>
            <p>
              Ends {new Date(competition.ends_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </p>
            <p>Status: {competition.finalized_at ? 'Frozen' : 'Open'}</p>
            <label className="as-console__field-label" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={competition.student_access}
                disabled={saving}
                onChange={(event) => void saveAccess(event.target.checked)}
              />
              Open LDR / QIZ / FLC Questions / ANL to students
            </label>
            <div style={{ display: 'flex', gap: 12, alignItems: 'end', marginTop: 16 }}>
              <label className="as-console__field">
                <span className="as-console__field-label">Platoon goal (optional)</span>
                <input
                  className="as-console__input"
                  value={goalDraft}
                  onChange={(event) => setGoalDraft(event.target.value)}
                  placeholder="Empty = no goal"
                />
              </label>
              <button type="button" className="button-secondary" disabled={saving} onClick={() => void saveGoal()}>
                Save goal
              </button>
            </div>
            <button
              type="button"
              className="button-primary"
              style={{ marginTop: 16 }}
              disabled={saving || Boolean(competition.finalized_at)}
              onClick={() => void freeze()}
            >
              Freeze final standings
            </button>
          </section>

          <section className="as-console__card" style={{ padding: 20 }}>
            <h2 className="as-console__card-title">Platoon dashboard</h2>
            <div className="ldr__platoon">
              <div>
                <span>Total AP</span>
                <strong>{dashboard.platoon_total_ap}</strong>
              </div>
              <div>
                <span>Mastered</span>
                <strong>{dashboard.concepts_mastered}</strong>
              </div>
              <div>
                <span>Accuracy</span>
                <strong>{dashboard.accuracy == null ? '—' : `${dashboard.accuracy}%`}</strong>
              </div>
              <div>
                <span>Participants</span>
                <strong>{dashboard.participants}</strong>
              </div>
              <div>
                <span>Completed exams</span>
                <strong>{dashboard.completed_exams}</strong>
              </div>
            </div>

            <h3 className="as-console__card-title" style={{ marginTop: 24 }}>
              By subject
            </h3>
            {dashboard.by_subject.length === 0 ? (
              <p>No scored answers yet.</p>
            ) : (
              <table className="ldr__table">
                <thead>
                  <tr>
                    <th>Subject</th>
                    <th>AP</th>
                    <th>Mastered</th>
                    <th>Accuracy</th>
                    <th>Answers</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.by_subject.map((row) => (
                    <tr key={`${row.subject_kind}:${row.subject_id}`}>
                      <td>{row.subject_name}</td>
                      <td>{row.lifetime_ap}</td>
                      <td>{row.concepts_mastered}</td>
                      <td>{row.accuracy == null ? '—' : `${row.accuracy}%`}</td>
                      <td>{row.questions_answered}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 className="as-console__card-title" style={{ marginTop: 24 }}>
              Standings
            </h3>
            <StandingsTable entries={dashboard.leaderboard} />
          </section>
        </div>
      )}
    </div>
  )
}
