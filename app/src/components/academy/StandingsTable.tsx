import { Info } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { LeaderboardEntry } from '../../lib/atlasApi'
import { REWARD_BANDS, groupByRewardBand } from '../../lib/leaderboardRewards'

export function StandingsTable({
  entries,
  selfName,
  showAccuracy = false,
}: {
  entries: LeaderboardEntry[]
  selfName?: string
  showAccuracy?: boolean
}) {
  const [rewardsOpen, setRewardsOpen] = useState(false)

  return (
    <div className="ldr__standings">
      <div className="ldr__standings-bar">
        <button
          type="button"
          className="ldr__rewards-btn"
          aria-haspopup="dialog"
          onClick={() => setRewardsOpen(true)}
        >
          <Info size={14} aria-hidden />
          Rewards
        </button>
      </div>
      <table className="ldr__table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Name</th>
            <th>AP</th>
            <th>Mastered</th>
            {showAccuracy ? <th>Accuracy</th> : null}
          </tr>
        </thead>
        {groupByRewardBand(entries).map(({ band, entries: rows }) => (
          <tbody key={band.id} className={`ldr__band ldr__band--${band.id}`} aria-label={band.label}>
            {rows.map((entry) => (
              <tr key={entry.user_id} className={selfName && entry.name === selfName ? 'is-you' : undefined}>
                <td>{entry.rank}</td>
                <td>{entry.name}</td>
                <td>{entry.lifetime_ap}</td>
                <td>{entry.concepts_mastered}</td>
                {showAccuracy ? <td>{entry.accuracy == null ? '—' : `${entry.accuracy}%`}</td> : null}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
      {rewardsOpen ? <RewardsDialog onClose={() => setRewardsOpen(false)} /> : null}
    </div>
  )
}

function RewardsDialog({ onClose }: { onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    panelRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="cal__dialog-backdrop" onClick={onClose} role="presentation">
      <div
        ref={panelRef}
        className="cal__dialog ldr__rewards"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ldr-rewards-title"
        tabIndex={-1}
        onClick={(click) => click.stopPropagation()}
      >
        <div className="cal__dialog-head">
          <h3 id="ldr-rewards-title" className="cal__dialog-title">
            Rewards
          </h3>
          <button type="button" className="cal__dialog-close" onClick={onClose}>
            Close
          </button>
        </div>
        <dl className="ldr__rewards-list">
          {REWARD_BANDS.filter((band) => band.reward).map((band) => (
            <div key={band.id} className={`ldr__rewards-item ldr__rewards-item--${band.id}`}>
              <dt>{band.label}</dt>
              <dd>{band.reward}</dd>
            </div>
          ))}
        </dl>
        <p className="ldr__rewards-note">
          Each place also earns every reward listed below it. 1st takes all three.
        </p>
      </div>
    </div>
  )
}
