import { ArrowDown, ArrowUp, Info } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { LeaderboardEntry } from '../../lib/atlasApi'
import { REWARD_BANDS, groupByRewardBand } from '../../lib/leaderboardRewards'

const POINT_RULES: readonly { label: string; points: string }[] = [
  { label: 'First correct answer', points: '+5 AP' },
  { label: 'Each repeat correct', points: '+1 AP' },
  { label: 'Mastery (5th correct)', points: '+3 AP bonus' },
  { label: 'Wrong answer', points: '0 AP' },
]

export function StandingsTable({
  entries,
  selfName,
  showAccuracy = false,
  showPointsInfo = false,
}: {
  entries: LeaderboardEntry[]
  selfName?: string
  showAccuracy?: boolean
  showPointsInfo?: boolean
}) {
  const [openDialog, setOpenDialog] = useState<'points' | 'rewards' | null>(null)
  const close = () => setOpenDialog(null)

  return (
    <div className="ldr__standings">
      <div className="ldr__standings-bar">
        {showPointsInfo ? (
          <button
            type="button"
            className="ldr__info-btn ldr__info-btn--start"
            aria-haspopup="dialog"
            onClick={() => setOpenDialog('points')}
          >
            <Info size={14} aria-hidden />
            How points work
          </button>
        ) : null}
        <button
          type="button"
          className="ldr__info-btn"
          aria-haspopup="dialog"
          onClick={() => setOpenDialog('rewards')}
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
            <th>24Hr</th>
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
                <td>
                  <Movement places={entry.movement_24h ?? 0} />
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
      {openDialog === 'rewards' ? (
        <InfoDialog id="ldr-rewards-title" title="Rewards" onClose={close}>
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
        </InfoDialog>
      ) : null}
      {openDialog === 'points' ? (
        <InfoDialog id="ldr-points-title" title="How points work" onClose={close}>
          <p className="ldr__rewards-note">Every question you answer earns Atlas Points (AP) by these rules.</p>
          <dl className="ldr__points-list">
            {POINT_RULES.map((rule) => (
              <div key={rule.label} className="ldr__points-item">
                <dt>{rule.label}</dt>
                <dd>{rule.points}</dd>
              </div>
            ))}
          </dl>
          <p className="ldr__rewards-note">
            Getting a question right five times masters it and earns 12 AP in total. Ties on AP go to more
            concepts mastered, then higher accuracy. Points stop when the challenge closes.
          </p>
        </InfoDialog>
      ) : null}
    </div>
  )
}

function Movement({ places }: { places: number }) {
  if (places > 0) {
    return (
      <span className="ldr__move ldr__move--up" aria-label={`Up ${places}`}>
        <ArrowUp size={14} aria-hidden />
        {places}
      </span>
    )
  }
  if (places < 0) {
    return (
      <span className="ldr__move ldr__move--down" aria-label={`Down ${-places}`}>
        <ArrowDown size={14} aria-hidden />
        {-places}
      </span>
    )
  }
  return (
    <span className="ldr__move ldr__move--flat" aria-label="No change">
      —
    </span>
  )
}

function InfoDialog({
  id,
  title,
  onClose,
  children,
}: {
  id: string
  title: string
  onClose: () => void
  children: ReactNode
}) {
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
        aria-labelledby={id}
        tabIndex={-1}
        onClick={(click) => click.stopPropagation()}
      >
        <div className="cal__dialog-head">
          <h3 id={id} className="cal__dialog-title">
            {title}
          </h3>
          <button type="button" className="cal__dialog-close" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
