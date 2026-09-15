import { createContext, useContext } from 'react'
import type {
  Artifact,
  Flashcard,
  ProductionRun,
  Quiz,
  Scenario,
  StageRun,
  Source,
  WikiEntry,
} from '../../lib/workspaceApi'

export interface WorkspaceDataContextValue {
  sources: Source[]
  productionRuns: ProductionRun[]
  stageRunsByRunId: Record<string, StageRun[]>
  artifacts: Artifact[]
  wikiEntries: WikiEntry[]
  flashcards: Flashcard[]
  quizzes: Quiz[]
  scenarios: Scenario[]
  isLoading: boolean
  error: string | null
  activeRunCount: number
  uploadSource: (file: File) => Promise<Source>
  uploadArtifact: (file: File) => Promise<Artifact>
  createProductionRun: (payload: {
    source_ids: string[]
    target_artifacts: string[]
  }) => Promise<ProductionRun>
  downloadArtifact: (artifactId: string) => Promise<void>
  addWikiEntry: (entry: WikiEntry) => void
  refresh: () => Promise<void>
}

export const WorkspaceDataContext = createContext<WorkspaceDataContextValue | undefined>(
  undefined,
)

export function useWorkspaceData(): WorkspaceDataContextValue {
  const context = useContext(WorkspaceDataContext)

  if (!context) {
    throw new Error('useWorkspaceData must be used within WorkspaceDataProvider.')
  }

  return context
}
