import type { LucideIcon } from 'lucide-react'
import { LogOut, MoreHorizontal } from 'lucide-react'
import { useState } from 'react'
import type { AcademyPage } from './types'

type DockItem = { id: AcademyPage; label: string; icon: LucideIcon; name?: string }

type AcademyDockProps = {
  items: DockItem[]
  activePage: string
  onSelect: (id: string) => void
  isAdmin: boolean
  isAcademy: boolean
  onToggleMode: () => void
  onSignOut: () => void
  displayEmail: string
}

/** Primary destinations stay in the dock; overflow + account live in More. */
const PRIMARY_LIMIT = 5

export function AcademyDock({
  items,
  activePage,
  onSelect,
  isAdmin,
  isAcademy,
  onToggleMode,
  onSignOut,
  displayEmail,
}: AcademyDockProps) {
  const [moreOpen, setMoreOpen] = useState(false)
  const primary = items.slice(0, PRIMARY_LIMIT)
  const overflow = items.slice(PRIMARY_LIMIT)
  const overflowActive = overflow.some((item) => item.id === activePage)

  const closeMore = () => setMoreOpen(false)

  return (
    <>
      <nav className="academy-dock" aria-label="Academy navigation">
        <div className="academy-dock__tabs">
          {primary.map((item) => {
            const Icon = item.icon
            const name = item.name ?? item.label
            return (
              <button
                key={item.id}
                type="button"
                className={`academy-dock__tab${activePage === item.id ? ' is-active' : ''}`}
                onClick={() => onSelect(item.id)}
                aria-current={activePage === item.id ? 'page' : undefined}
                aria-label={name}
              >
                <Icon size={20} strokeWidth={1.75} aria-hidden />
                <span>{item.label}</span>
              </button>
            )
          })}
          <button
            type="button"
            className={`academy-dock__tab${moreOpen || overflowActive ? ' is-active' : ''}`}
            onClick={() => setMoreOpen((open) => !open)}
            aria-expanded={moreOpen}
            aria-label="More"
          >
            <MoreHorizontal size={20} strokeWidth={1.75} aria-hidden />
            <span>MORE</span>
          </button>
        </div>
      </nav>

      {moreOpen && (
        <div className="academy-dock__sheet-backdrop" onClick={closeMore} role="presentation">
          <div
            className="academy-dock__sheet"
            role="dialog"
            aria-modal="true"
            aria-label="More Academy options"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="academy-dock__sheet-handle" aria-hidden />
            <p className="academy-dock__sheet-title">More</p>
            {overflow.length > 0 && (
              <ul className="academy-dock__sheet-list">
                {overflow.map((item) => {
                  const Icon = item.icon
                  const name = item.name ?? item.label
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={`academy-dock__sheet-item${activePage === item.id ? ' is-active' : ''}`}
                        onClick={() => {
                          onSelect(item.id)
                          closeMore()
                        }}
                        aria-current={activePage === item.id ? 'page' : undefined}
                      >
                        <Icon size={18} strokeWidth={1.75} aria-hidden />
                        <span>{name}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
            {isAdmin && (
              <button
                type="button"
                className="academy-dock__sheet-item"
                onClick={() => {
                  onToggleMode()
                  closeMore()
                }}
              >
                <span className="academy-dock__mode-mark">{isAcademy ? 'F' : 'A'}</span>
                <span>{isAcademy ? 'Switch to Foundry' : 'Switch to Academy'}</span>
              </button>
            )}
            <button
              type="button"
              className="academy-dock__sheet-item academy-dock__sheet-item--danger"
              onClick={() => {
                closeMore()
                onSignOut()
              }}
              title={`Sign out (${displayEmail})`}
            >
              <LogOut size={18} strokeWidth={1.75} aria-hidden />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </>
  )
}
