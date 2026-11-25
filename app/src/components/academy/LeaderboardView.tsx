import { useEffect, useState } from 'react'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { getLeaderboard, type Leaderboard } from '../../lib/atlasApi'
import { Loader } from '../shared/Loader'
import { StandingsTable } from './StandingsTable'
import { StudyHead } from './StudySessionChrome'

export function LeaderboardView() {
  const { activeWorkspace } = useWorkspace()
  const { approvedUser, user } = useAuth()
  const [board, setBoard] = useState<Leaderboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!activeWorkspace) return
    let cancelled = false
    void getLeaderboard(activeWorkspace.id)
      .then((next) => {
        if (!cancelled) {
          setBoard(next)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Could not load the leaderboard.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [activeWorkspace])

  const selfName = approvedUser?.name ?? approvedUser?.email ?? user?.email ?? ''
  const ends = board ? new Date(board.ends_at) : null

  return (
    <section className="ldr study-session">
      <StudyHead
        eyebrow="Atlas Points"
        title="Leaderboard"
        description="Platoon standings for the Academic Challenge. Lifetime Atlas Points decide the order."
      />

      {error ? <p className="lib__empty">{error}</p> : null}
      {!board && !error ? (
        <div className="lib__empty">
          <Loader label="Loading leaderboard" size="sm" />
        </div>
      ) : null}

      {board ? (
        <>
          {board.finalized ? (
            <p className="ldr__frozen">Challenge closed. Final standings.</p>
          ) : ends ? (
            <p className="ldr__frozen">
              Challenge ends {ends.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </p>
          ) : null}

          <div className={`ldr__platoon${board.platoon_goal != null ? ' ldr__platoon--goal' : ''}`}>
            <div>
              <span>Platoon total</span>
              <strong>{board.platoon_total_ap.toLocaleString()} AP</strong>
            </div>
            {board.platoon_goal != null ? (
              <div>
                <span>Goal</span>
                <strong>{board.platoon_goal.toLocaleString()} AP</strong>
              </div>
            ) : null}
            {board.platoon_goal != null ? (
              <div
                className="ldr__meter"
                role="meter"
                aria-valuemin={0}
                aria-valuemax={board.platoon_goal}
                aria-valuenow={Math.min(board.platoon_total_ap, board.platoon_goal)}
                aria-label="Platoon progress toward the goal"
              >
                <div
                  style={{
                    width: `${Math.min(100, (board.platoon_total_ap / board.platoon_goal) * 100)}%`,
                  }}
                />
              </div>
            ) : null}
          </div>

          <StandingsTable entries={board.entries} selfName={selfName} showAccuracy showPointsInfo />
        </>
      ) : null}
    </section>
  )
}
