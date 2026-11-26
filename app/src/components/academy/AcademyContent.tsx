import { useMemo } from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { defaultReaderSourceId, useOutputs } from '../../lib/academyOutputs'
import { useLibraryFocus } from '../../lib/libraryFocus'
import { AcademyChromeProvider } from './academyChromeContext'
import { CalendarView } from './CalendarView'
import { DiscussionsView } from './DiscussionsView'
import { FlashcardsView } from './FlashcardsView'
import { LibraryView } from './LibraryView'
import { ObjectivesView } from './ObjectivesView'
import { AnalyticsView } from './AnalyticsView'
import { LeaderboardView } from './LeaderboardView'
import { QuizView } from './QuizView'
import { ReaderView } from './ReaderView'
import { ScenarioView } from './ScenarioView'
import { AcademyWiki } from './AcademyWiki'
import type { AcademyPage, AcademyScope } from './types'

type AcademyContentProps = {
  page: AcademyPage
  sourceId?: string | null
  seg?: number | null
  lessonId?: string | null
  resourceId?: string | null
  scope: AcademyScope
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
  compact?: boolean
}

export function AcademyContent({
  page,
  sourceId = null,
  seg = null,
  lessonId = null,
  resourceId = null,
  scope,
  onOpen,
  compact = false,
}: AcademyContentProps) {
  const { activeWorkspace } = useWorkspace()
  const { focus } = useLibraryFocus(activeWorkspace?.id ?? null)
  const { items } = useOutputs()
  // A reader link wins. Otherwise open the favorited ebook, then the
  // platoon default (MCDP 1 Warfighting), then the first book by name.
  const readerSourceId = defaultReaderSourceId({
    routeSourceId: sourceId,
    focusedSourceId: focus.ebookSourceId,
    books: items.filter((item) => item.isEbook),
    workspaceName: activeWorkspace?.name ?? null,
  })
  const chrome = useMemo(() => ({ compact }), [compact])

  return (
    <AcademyChromeProvider value={chrome}>
      <div className={`academy academy--integrated${compact ? ' academy--compact' : ''}`}>
        <div className="academy__main">
          {page === 'leaderboard' && <LeaderboardView />}
          {page === 'library' && <LibraryView onOpen={onOpen} />}
          {page === 'reader' && <ReaderView sourceId={readerSourceId} seg={seg} onOpen={onOpen} />}
          {page === 'wiki' && (
            <AcademyWiki
              sourceId={scope.sourceId}
              targetId={scope.targetId}
              wikiKind={scope.wikiKind ?? null}
            />
          )}
          {page === 'flashcards' && (
            <FlashcardsView
              sourceId={scope.sourceId}
              targetId={scope.targetId}
              projectId={scope.projectId}
            />
          )}
          {page === 'quiz' && (
            <QuizView
              key={`${scope.sourceId ?? ''}:${scope.lessonId ?? ''}:${scope.projectId ?? ''}:${scope.batchKey ?? ''}`}
              sourceId={scope.sourceId}
              lessonId={scope.lessonId ?? null}
            />
          )}
          {page === 'analytics' && <AnalyticsView />}
          {page === 'scenarios' && (
            <ScenarioView
              sourceId={scope.sourceId}
              targetId={scope.targetId}
              projectId={scope.projectId}
            />
          )}
          {page === 'discussions' && (
            <DiscussionsView sourceId={scope.sourceId} threadId={scope.threadId ?? null} />
          )}
          {page === 'calendar' && <CalendarView />}
          {page === 'objectives' && (
            <ObjectivesView
              key={lessonId ?? 'all'}
              focusLessonId={lessonId}
              focusResourceId={resourceId}
              onOpen={onOpen}
            />
          )}
        </div>
      </div>
    </AcademyChromeProvider>
  )
}
