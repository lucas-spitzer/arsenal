import { LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { matchPath, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AcademyContent } from '../academy/AcademyContent'
import {
  emptyAcademyScope,
  academyRailItems,
  type AcademyPage,
  type AcademyScope,
} from '../academy/types'
import { signOut } from '../../features/auth/authService'
import { useAuth } from '../../features/auth/authContext'
import { FoundryArtifacts } from './FoundryArtifacts'
import { FoundryAssessments } from './FoundryAssessments'
import { FoundryOps } from './FoundryOps'
import { FoundryStages } from './FoundryStages'
import { FoundrySources } from './FoundrySources'
import { FoundryStageSettings } from './FoundryStageSettings'
import { FoundryWorkspaces } from './FoundryWorkspaces'
import { railIconSize, railItems, type FoundryPage } from './types'

type AppMode = 'foundry' | 'academy'

const SHELL_STORAGE_KEY = 'arsenal.foundryShell'

const foundryPageIds = new Set(railItems.map((item) => item.id))
const academyRailPageIds = new Set(academyRailItems.map((item) => item.id))
const academyPageIds = new Set<AcademyPage>([...academyRailPageIds, 'wiki'])

type ShellState = {
  mode: AppMode
  foundryPage: FoundryPage
  academyPage: AcademyPage
  academyScope: AcademyScope
}

const defaultShellState: ShellState = {
  mode: 'foundry',
  foundryPage: 'ops',
  academyPage: 'library',
  academyScope: emptyAcademyScope,
}

function readShellState(): ShellState {
  try {
    const raw = sessionStorage.getItem(SHELL_STORAGE_KEY)
    if (!raw) return defaultShellState
    const parsed = JSON.parse(raw) as Partial<ShellState>
    const mode = parsed.mode === 'academy' || parsed.mode === 'foundry' ? parsed.mode : 'foundry'
    const foundryPage =
      typeof parsed.foundryPage === 'string' && foundryPageIds.has(parsed.foundryPage as FoundryPage)
        ? (parsed.foundryPage as FoundryPage)
        : 'ops'
    const academyPage =
      typeof parsed.academyPage === 'string' && academyPageIds.has(parsed.academyPage as AcademyPage)
        ? (parsed.academyPage as AcademyPage)
        : 'library'
    const scope = parsed.academyScope
    const academyScope: AcademyScope =
      scope && typeof scope === 'object'
        ? {
            sourceId: typeof scope.sourceId === 'string' ? scope.sourceId : null,
            targetId: typeof scope.targetId === 'string' ? scope.targetId : null,
          }
        : emptyAcademyScope
    return { mode, foundryPage, academyPage, academyScope }
  } catch {
    return defaultShellState
  }
}

export function FoundryShell() {
  const [shell, setShell] = useState<ShellState>(readShellState)
  const { mode, foundryPage, academyPage, academyScope } = shell
  const { approvedUser, user } = useAuth()
  const displayEmail = approvedUser?.email ?? user?.email ?? 'Signed in'

  useEffect(() => {
    sessionStorage.setItem(SHELL_STORAGE_KEY, JSON.stringify(shell))
  }, [shell])

  const setMode = (next: AppMode | ((prev: AppMode) => AppMode)) => {
    setShell((shellState) => ({
      ...shellState,
      mode: typeof next === 'function' ? next(shellState.mode) : next,
    }))
  }
  const setFoundryPage = (nextPage: FoundryPage) => {
    setShell((shellState) => ({ ...shellState, foundryPage: nextPage }))
  }
  const setAcademyPage = (nextPage: AcademyPage) => {
    setShell((shellState) => ({ ...shellState, academyPage: nextPage }))
  }
  const setAcademyScope = (nextScope: AcademyScope) => {
    setShell((shellState) => ({ ...shellState, academyScope: nextScope }))
  }

  // Reader is the one URL-addressable screen: /app/reader/:sourceId?seg=N.
  // When that route is active it overrides the state-driven tabs.
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const readerMatch = matchPath('/app/reader/:sourceId', location.pathname)
  const routedSourceId = readerMatch?.params.sourceId ?? null
  const segParam = searchParams.get('seg')
  const parsedSeg = segParam != null && segParam !== '' ? Number.parseInt(segParam, 10) : NaN
  const seg = Number.isFinite(parsedSeg) ? parsedSeg : null

  const isAcademy = routedSourceId ? true : mode === 'academy'
  const activeAcademyPage: AcademyPage = routedSourceId ? 'reader' : academyPage
  const navItems = isAcademy ? academyRailItems : railItems
  const activePage = isAcademy ? activeAcademyPage : foundryPage

  const toggleMode = () => {
    if (routedSourceId) {
      navigate('/app', { replace: true })
      setMode('foundry')
      return
    }
    setMode((m) => (m === 'foundry' ? 'academy' : 'foundry'))
  }

  const setPage = (id: string) => {
    if (routedSourceId) {
      navigate('/app', { replace: true })
      setMode('academy')
    }
    if (isAcademy) {
      setAcademyScope(emptyAcademyScope) // rail navigation clears any open-from-Library scope
      setAcademyPage(id as AcademyPage)
    } else {
      setFoundryPage(id as FoundryPage)
    }
  }

  // Open a runner from the Library, carrying a source filter + focus target.
  const openAcademy = (page: AcademyPage, scope: AcademyScope) => {
    if (routedSourceId) navigate('/app', { replace: true })
    setMode('academy')
    setAcademyScope(scope)
    setAcademyPage(page)
  }

  return (
    <div className={`as-console${isAcademy ? ' as-console--academy' : ''}`}>
      <nav
        className="as-console__rail"
        aria-label={isAcademy ? 'Academy navigation' : 'Foundry navigation'}
      >
        <button
          type="button"
          className={`as-console__rail-mark${isAcademy ? ' is-academy' : ''}`}
          onClick={toggleMode}
          title={isAcademy ? 'Switch to Foundry' : 'Switch to Academy'}
          aria-label={isAcademy ? 'Academy — switch to Foundry' : 'Foundry — switch to Academy'}
        >
          {isAcademy ? 'A' : 'F'}
        </button>
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              className={`as-console__rail-btn${activePage === item.id ? ' is-active' : ''}`}
              onClick={() => setPage(item.id)}
              aria-current={activePage === item.id ? 'page' : undefined}
            >
              <Icon className="as-console__rail-icon" size={railIconSize} strokeWidth={1.75} aria-hidden />
              {item.label}
            </button>
          )
        })}

        <div className="as-console__rail-foot">
          <button
            type="button"
            className="as-console__rail-btn as-console__rail-btn--account"
            onClick={() => void signOut()}
            title={`Sign out (${displayEmail})`}
          >
            <LogOut className="as-console__rail-icon" size={railIconSize} strokeWidth={1.75} aria-hidden />
            OUT
          </button>
        </div>
      </nav>

      <div className="as-console__main">
        {isAcademy ? (
          <AcademyContent
            page={activeAcademyPage}
            sourceId={routedSourceId}
            seg={seg}
            scope={academyScope}
            onOpen={openAcademy}
          />
        ) : (
          <>
            {foundryPage === 'ops' ? <FoundryOps onGoToSources={() => setFoundryPage('sources')} /> : null}
            {foundryPage === 'sources' ? <FoundrySources /> : null}
            {foundryPage === 'stages' ? <FoundryStages /> : null}
            {foundryPage === 'artifacts' ? <FoundryArtifacts /> : null}
            {foundryPage === 'assessments' ? <FoundryAssessments onOpen={openAcademy} /> : null}
            {foundryPage === 'workspace' ? <FoundryWorkspaces /> : null}
            {foundryPage === 'settings' ? <FoundryStageSettings /> : null}
          </>
        )}
      </div>
    </div>
  )
}
