import { useEffect, useId, useRef, useState } from 'react'
import { signOut } from '../../features/auth/authService'
import { useAuth } from '../../features/auth/authContext'
import { useAtlas } from '../../features/atlas/atlasContext'
import { RankMark } from './RankMark'

export function StudentIdentity() {
  const { approvedUser, user } = useAuth()
  const { me } = useAtlas()
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const rootRef = useRef<HTMLDivElement>(null)

  const name = approvedUser?.name ?? approvedUser?.email ?? user?.email ?? 'Student'
  const rank = approvedUser?.rank ?? null
  const ap = me?.lifetime_ap ?? 0

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onPointer)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="id-plate" ref={rootRef}>
      <button
        type="button"
        className="id-plate__btn"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <RankMark rank={rank} />
        <span className="id-plate__who">
          <strong>{name}</strong>
        </span>
        <span className="id-plate__ap" aria-label={`${ap} Atlas Points`}>
          <em>{ap}</em>
          AP
        </span>
      </button>
      {open ? (
        <div className="id-plate__sheet" id={panelId} role="dialog" aria-label="Account">
          <div className="id-plate__sheet-head">
            <RankMark rank={rank} size={40} />
            <div>
              <strong>{name}</strong>
              <p>Atlas Points</p>
            </div>
          </div>
          <dl className="id-plate__stats">
            <div>
              <dt>Lifetime AP</dt>
              <dd>{ap}</dd>
            </div>
            <div>
              <dt>Mastered</dt>
              <dd>{me?.concepts_mastered ?? 0}</dd>
            </div>
          </dl>
          <p className="id-plate__note">Earned marks will appear here later.</p>
          <button type="button" className="id-plate__signout" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  )
}
