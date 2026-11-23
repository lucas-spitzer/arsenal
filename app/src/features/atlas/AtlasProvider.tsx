import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from '../../lib/apiClient'
import { getAtlasAccess, getAtlasMe, type AtlasMe } from '../../lib/atlasApi'
import { isAdminAccess } from '../auth/access'
import { useAuth } from '../auth/authContext'
import { useWorkspace } from '../workspace/workspaceContext'
import { AtlasContext } from './atlasContext'

const emptyMe: AtlasMe = {
  lifetime_ap: 0,
  concepts_mastered: 0,
  accuracy: null,
  questions_answered: 0,
  correct_answers: 0,
}

export function AtlasProvider({ children }: { children: ReactNode }) {
  const { activeWorkspace } = useWorkspace()
  const { approvedUser } = useAuth()
  const isAdmin = isAdminAccess(approvedUser?.role)
  const workspaceId = activeWorkspace?.id ?? null
  const [me, setMe] = useState<AtlasMe | null>(null)
  const [studentAccess, setStudentAccess] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadToken, setLoadToken] = useState(0)

  const refresh = useCallback(async () => {
    setLoadToken((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!workspaceId) {
      queueMicrotask(() => {
        if (cancelled) return
        setMe(null)
        setStudentAccess(false)
        setError(null)
        setIsLoading(false)
      })
      return () => {
        cancelled = true
      }
    }

    void getAtlasAccess(workspaceId)
      .then(async (access) => {
        if (cancelled) return
        setStudentAccess(Boolean(access.student_access))
        setIsLoading(true)
        setError(null)
        if (isAdmin || access.student_access) {
          const next = await getAtlasMe(workspaceId)
          if (!cancelled) setMe(next)
        } else if (!cancelled) {
          setMe(emptyMe)
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        if (caught instanceof ApiError && caught.status === 403 && !isAdmin) {
          setMe(emptyMe)
          setError(null)
        } else {
          setMe(isAdmin ? emptyMe : null)
          setError(caught instanceof Error ? caught.message : 'Could not load Atlas Points.')
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [workspaceId, isAdmin, loadToken])

  const setLifetimeAp = useCallback((lifetimeAp: number) => {
    setMe((current) => ({ ...(current ?? emptyMe), lifetime_ap: lifetimeAp }))
  }, [])

  const value = useMemo(
    () => ({ me, studentAccess, isLoading, error, refresh, setLifetimeAp }),
    [me, studentAccess, isLoading, error, refresh, setLifetimeAp],
  )

  return <AtlasContext.Provider value={value}>{children}</AtlasContext.Provider>
}
