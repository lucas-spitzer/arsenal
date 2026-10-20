import { useWorkspace } from '../../features/workspace/workspaceContext'
import { defaultReaderSourceId, useOutputs } from '../../lib/academyOutputs'
import { useLibraryFocus } from '../../lib/libraryFocus'
import { DiscussionsView } from './DiscussionsView'
import { FlashcardsView } from './FlashcardsView'
import { LibraryView } from './LibraryView'
import { QuizView } from './QuizView'
import { ReaderView } from './ReaderView'
import { ScenarioView } from './ScenarioView'
import { AcademyWiki } from './AcademyWiki'
import type { AcademyPage, AcademyScope } from './types'

type AcademyContentProps = {
  page: AcademyPage
  sourceId?: string | null
  seg?: number | null
  scope: AcademyScope
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}

export function AcademyContent({ page, sourceId = null, seg = null, scope, onOpen }: AcademyContentProps) {
  const { activeWorkspace } = useWorkspace()
  const { focus } = useLibraryFocus(activeWorkspace?.id ?? null)
  const { items } = useOutputs()
  // A reader link wins. Otherwise open the favorited ebook, then the first book.
  const readerSourceId = defaultReaderSourceId({
    routeSourceId: sourceId,
    focusedSourceId: focus.ebookSourceId,
    books: items.filter((item) => item.isEbook),
  })

  return (
    <div className="academy academy--integrated">
      <div className="academy__main">
        {page === 'library' && <LibraryView onOpen={onOpen} />}
        {page === 'reader' && <ReaderView sourceId={readerSourceId} seg={seg} onOpen={onOpen} />}
        {page === 'wiki' && <AcademyWiki sourceId={scope.sourceId} targetId={scope.targetId} />}
        {page === 'flashcards' && (
          <FlashcardsView
            sourceId={scope.sourceId}
            targetId={scope.targetId}
            projectId={scope.projectId}
          />
        )}
        {page === 'quiz' && (
          <QuizView sourceId={scope.sourceId} targetId={scope.targetId} projectId={scope.projectId} />
        )}
        {page === 'scenarios' && (
          <ScenarioView
            sourceId={scope.sourceId}
            targetId={scope.targetId}
            projectId={scope.projectId}
          />
        )}
        {page === 'discussions' && <DiscussionsView sourceId={scope.sourceId} />}
      </div>
    </div>
  )
}
