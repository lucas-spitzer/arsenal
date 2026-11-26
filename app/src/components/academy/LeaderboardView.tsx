import { useEffect, useState } from 'react'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { getLeaderboard, type Leaderboard } from '../../lib/atlasApi'
import { onPageReturn } from '../../lib/refreshOnReturn'
import { Loader } from '../shared/Loader'
import { StandingsTable } from './StandingsTable'
import { StudyHead } from './StudySessionChrome'

export function LeaderboardView() {
  const { activeWorkspace } = useWorkspace()
  const { approvedUser, user } = useAuth()
  const [board, setBoard] = useState<Leaderboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  const workspaceId = activeWorkspace?.id ?? null

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    let latest = 0
    const load = () => {
      const request = ++latest
      void getLeaderboard(workspaceId)
        .then((next) => {
          if (!cancelled && request === latest) {
            setBoard(next)
            setError(null)
          }
        })
        .catch((caught: unknown) => {
          if (!cancelled && request === latest) {
            setError(caught instanceof Error ? caught.message : 'Could not load the leaderboard.')
          }
        })
    }
    load()
    const unsubscribe = onPageReturn(load)
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [workspaceId])

  const selfName = approvedUser?.name ?? approvedUser?.email ?? user?.email ?? ''

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
          ) : (
            <p className="ldr__frozen">Challenge ends Nov 30, 2026, 2200</p>
          )}

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
