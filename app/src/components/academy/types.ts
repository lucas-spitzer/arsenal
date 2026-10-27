import type { LucideIcon } from 'lucide-react'
import {
  BookOpen,
  CalendarDays,
  HelpCircle,
  Layers,
  Library,
  Lightbulb,
  MessageSquare,
  Target,
} from 'lucide-react'

export type AcademyPage =
  | 'library'
  | 'reader'
  | 'wiki'
  | 'flashcards'
  | 'quiz'
  | 'scenarios'
  | 'discussions'
  | 'calendar'
  | 'objectives'

// Scope passed when opening a runner from the Library (filter + focus target).
export type AcademyScope = {
  sourceId: string | null
  targetId: string | null
  /** Knowledge run to study. Null opens the whole source, or every record from the rail. */
  projectId: string | null
  /** Discussions thread to open, e.g. one started from "Discuss this class". */
  threadId?: string | null
}

export const emptyAcademyScope: AcademyScope = { sourceId: null, targetId: null, projectId: null, threadId: null }

export const academyRailItems: { id: AcademyPage; label: string; icon: LucideIcon }[] = [
  { id: 'library', label: 'LIB', icon: Library },
  { id: 'reader', label: 'RDR', icon: BookOpen },
  { id: 'calendar', label: 'CAL', icon: CalendarDays },
  { id: 'objectives', label: 'ELO', icon: Target },
  { id: 'discussions', label: 'DSC', icon: MessageSquare },
  { id: 'flashcards', label: 'FLC', icon: Layers },
  { id: 'quiz', label: 'QIZ', icon: HelpCircle },
  { id: 'scenarios', label: 'SCN', icon: Lightbulb },
]

// TBS students write their own study guides. These runners stay on the admin Academy rail.
const studentHiddenAcademyPages = new Set<AcademyPage>(['flashcards', 'quiz', 'scenarios'])

export function academyRailForRole(isAdmin: boolean) {
  if (isAdmin) return academyRailItems
  return academyRailItems.filter((item) => !studentHiddenAcademyPages.has(item.id))
}

export function academyPageForRole(page: AcademyPage, isAdmin: boolean): AcademyPage {
  if (isAdmin || !studentHiddenAcademyPages.has(page)) return page
  return 'library'
}
