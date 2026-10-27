import { useCallback, useEffect, useState } from 'react'
import { listLessons, type Lesson } from './lessonsApi'

type LessonsResult = { key: string; lessons: Lesson[]; error: string | null }

const NO_LESSONS: Lesson[] = []

/** Academy ELO classes for a workspace. `reload` refetches after an edit. */
export function useLessons(workspaceId: string | null) {
  const [reloadToken, setReloadToken] = useState(0)
  const [result, setResult] = useState<LessonsResult | null>(null)
  const requestKey = workspaceId ? `${workspaceId}:${reloadToken}` : null

  useEffect(() => {
    if (!workspaceId || !requestKey) return
    let cancelled = false
    listLessons(workspaceId)
      .then((lessons) => {
        if (!cancelled) setResult({ key: requestKey, lessons, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Could not load ELOs.'
        setResult({ key: requestKey, lessons: [], error: message })
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, requestKey])

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  return {
    lessons: result?.lessons ?? NO_LESSONS,
    error: result?.error ?? null,
    hasLoaded: result !== null,
    isLoading: result?.key !== requestKey,
    reload,
  }
}
