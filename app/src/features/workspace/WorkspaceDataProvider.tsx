import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  createProductionRun as createProductionRunRequest,
  deleteProductionRun as deleteProductionRunRequest,
  getArtifactDownloadUrl,
  listArtifacts,
  listFlashcards,
  listProductionRuns,
  listQuizzes,
  listScenarios,
  listStageRuns,
  listSources,
  listKnowledgeRunTitles,
  listWikiEntries,
  uploadSource as uploadSourceRequest,
  uploadStructuredData as uploadStructuredDataRequest,
  uploadArtifact as uploadArtifactRequest,
  type Artifact,
  type Flashcard,
  type ProductionRun,
  type Quiz,
  type Scenario,
  type StageRun,
  type Source,
  type KnowledgeRunTitle,
  type WikiEntry,
} from '../../lib/workspaceApi'
import { collapseDuplicateNarrationArtifacts } from '../../lib/foundryMappers'
import { isAdminAccess } from '../auth/access'
import { useAuth } from '../auth/authContext'
import { useWorkspace } from './workspaceContext'
import { WorkspaceDataContext } from './workspaceDataContext'

const POLL_INTERVAL_MS = 5000
const ACTIVE_STATUSES = new Set(['queued', 'running'])

interface WorkspaceDataProviderProps {
  children: ReactNode
}

export function WorkspaceDataProvider({ children }: WorkspaceDataProviderProps) {
  const { activeWorkspace } = useWorkspace()
  const { approvedUser } = useAuth()
  const isAdmin = isAdminAccess(approvedUser?.role)
  const workspaceId = activeWorkspace?.id ?? null

  const [sources, setSources] = useState<Source[]>([])
  const [structuredSources, setStructuredSources] = useState<Source[]>([])
  const [productionRuns, setProductionRuns] = useState<ProductionRun[]>([])
  const [stageRunsByRunId, setStageRunsByRunId] = useState<Record<string, StageRun[]>>({})
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [wikiEntries, setWikiEntries] = useState<WikiEntry[]>([])
  const [flashcards, setFlashcards] = useState<Flashcard[]>([])
  const [quizzes, setQuizzes] = useState<Quiz[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [knowledgeRunTitles, setKnowledgeRunTitles] = useState<KnowledgeRunTitle[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshInFlight = useRef(false)
  const workspaceIdRef = useRef(workspaceId)
  workspaceIdRef.current = workspaceId

  const refresh = useCallback(async () => {
    if (!workspaceId || refreshInFlight.current) {
      return
    }

    const refreshWorkspaceId = workspaceId
    refreshInFlight.current = true
    setIsLoading(true)
    setError(null)

    try {
      const [
        nextSources,
        nextArtifacts,
        nextWikiEntries,
        nextFlashcards,
        nextQuizzes,
        nextScenarios,
        nextKnowledgeRunTitles,
      ] = await Promise.all([
        listSources(refreshWorkspaceId),
        listArtifacts(refreshWorkspaceId),
        listWikiEntries(refreshWorkspaceId),
        listFlashcards(refreshWorkspaceId),
        listQuizzes(refreshWorkspaceId),
        listScenarios(refreshWorkspaceId),
        listKnowledgeRunTitles(refreshWorkspaceId),
      ])

      const nextRuns = isAdmin ? await listProductionRuns(refreshWorkspaceId) : []
      const stageRunEntries = isAdmin
        ? await Promise.all(
            nextRuns.map(async (run) => [run.id, await listStageRuns(run.id)] as const),
          )
        : []

      // Drop stale results if the active workspace changed mid-flight.
      if (refreshWorkspaceId !== workspaceIdRef.current) {
        return
      }

      setSources(nextSources.filter((source) => source.source_kind !== 'structured_data'))
      setStructuredSources(nextSources.filter((source) => source.source_kind === 'structured_data'))
      setProductionRuns(nextRuns)
      setStageRunsByRunId(Object.fromEntries(stageRunEntries))
      setArtifacts(collapseDuplicateNarrationArtifacts(nextArtifacts))
      setWikiEntries(nextWikiEntries)
      setFlashcards(nextFlashcards)
      setQuizzes(nextQuizzes)
      setScenarios(nextScenarios)
      setKnowledgeRunTitles(nextKnowledgeRunTitles)
    } catch (loadError) {
      if (refreshWorkspaceId !== workspaceIdRef.current) {
        return
      }
      setError(loadError instanceof Error ? loadError.message : 'Failed to load workspace data.')
    } finally {
      if (refreshWorkspaceId === workspaceIdRef.current) {
        setIsLoading(false)
      }
      refreshInFlight.current = false
    }
  }, [isAdmin, workspaceId])

  useEffect(() => {
    if (!workspaceId) {
      setSources([])
      setStructuredSources([])
      setProductionRuns([])
      setStageRunsByRunId({})
      setArtifacts([])
      setWikiEntries([])
      setFlashcards([])
      setQuizzes([])
      setScenarios([])
      setKnowledgeRunTitles([])
      setError(null)
      setIsLoading(false)
      return
    }

    void refresh()
  }, [workspaceId, refresh])

  const activeRunCount = useMemo(
    () =>
      productionRuns.filter((run) => ACTIVE_STATUSES.has(run.status)).length,
    [productionRuns],
  )

  useEffect(() => {
    if (!workspaceId || activeRunCount === 0) {
      return
    }

    const intervalId = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)

    return () => window.clearInterval(intervalId)
  }, [workspaceId, activeRunCount, refresh])

  const uploadSource = useCallback(
    async (file: File) => {
      if (!workspaceId) {
        throw new Error('No active workspace.')
      }

      const source = await uploadSourceRequest(workspaceId, file)
      await refresh()
      return source
    },
    [workspaceId, refresh],
  )

  const uploadStructuredData = useCallback(
    async (file: File) => {
      if (!workspaceId) {
        throw new Error('No active workspace.')
      }

      const source = await uploadStructuredDataRequest(workspaceId, file)
      await refresh()
      return source
    },
    [workspaceId, refresh],
  )

  const uploadArtifact = useCallback(
    async (file: File) => {
      if (!workspaceId) {
        throw new Error('No active workspace.')
      }

      const artifact = await uploadArtifactRequest(workspaceId, file)
      await refresh()
      return artifact
    },
    [workspaceId, refresh],
  )

  const createProductionRun = useCallback(
    async (payload: {
      source_ids: string[]
      target_artifacts: string[]
      narration_restart_source_ids?: string[]
    }) => {
      if (!workspaceId) {
        throw new Error('No active workspace.')
      }

      const run = await createProductionRunRequest(workspaceId, payload)
      await refresh()
      return run
    },
    [workspaceId, refresh],
  )

  const deleteProductionRun = useCallback(
    async (runId: string) => {
      if (!workspaceId) {
        throw new Error('No active workspace.')
      }

      await deleteProductionRunRequest(workspaceId, runId)
      await refresh()
    },
    [workspaceId, refresh],
  )

  const downloadArtifact = useCallback(async (artifactId: string) => {
    const { download_url } = await getArtifactDownloadUrl(artifactId)
    window.open(download_url, '_blank', 'noopener,noreferrer')
  }, [])

  const addWikiEntry = useCallback((entry: WikiEntry) => {
    setWikiEntries((prev) => {
      if (prev.some((existing) => existing.id === entry.id)) {
        return prev.map((existing) => (existing.id === entry.id ? entry : existing))
      }
      return [...prev, entry]
    })
  }, [])

  const value = useMemo(
    () => ({
      sources,
      structuredSources,
      productionRuns,
      stageRunsByRunId,
      artifacts,
      wikiEntries,
      flashcards,
      quizzes,
      scenarios,
      knowledgeRunTitles,
      isLoading,
      error,
      activeRunCount,
      uploadSource,
      uploadStructuredData,
      uploadArtifact,
      createProductionRun,
      deleteProductionRun,
      downloadArtifact,
      addWikiEntry,
      refresh,
    }),
    [
      sources,
      structuredSources,
      productionRuns,
      stageRunsByRunId,
      artifacts,
      wikiEntries,
      flashcards,
      quizzes,
      scenarios,
      knowledgeRunTitles,
      isLoading,
      error,
      activeRunCount,
      uploadSource,
      uploadStructuredData,
      uploadArtifact,
      createProductionRun,
      deleteProductionRun,
      downloadArtifact,
      addWikiEntry,
      refresh,
    ],
  )

  return <WorkspaceDataContext.Provider value={value}>{children}</WorkspaceDataContext.Provider>
}
