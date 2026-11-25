import type { LucideIcon } from 'lucide-react'
import {
  BookOpen,
  CalendarDays,
  ChartColumn,
  HelpCircle,
  Layers,
  Library,
  MessageSquare,
  Trophy,
} from 'lucide-react'

export type AcademyPage =
  | 'leaderboard'
  | 'library'
  | 'reader'
  | 'wiki'
  | 'flashcards'
  | 'quiz'
  | 'scenarios'
  | 'discussions'
  | 'calendar'
  | 'objectives'
  | 'analytics'

// Scope passed when opening a runner from the Library (filter + focus target).
export type AcademyScope = {
  sourceId: string | null
  targetId: string | null
  /** Class to scope to. Quiz opens a Subject Exam on it. */
  lessonId?: string | null
  /** Knowledge run to study. Null opens the whole source, or every record from the rail. */
  projectId: string | null
  /** Discussions thread to open, e.g. one started from "Discuss this class". */
  threadId?: string | null
  /** Quiz batch to open. An `unassigned:` key selects questions with no knowledge batch. */
  batchKey?: string | null
  /** Wiki page limited to knowledge ELOs for the source. Null shows every other entry. */
  wikiKind?: 'elo' | null
}

export const emptyAcademyScope: AcademyScope = { sourceId: null, targetId: null, projectId: null, threadId: null }

/** Quiz launch state from a scope: a class or book opens Subject Exam on it. */
export function quizLaunchFromScope(scope: Pick<AcademyScope, 'sourceId' | 'lessonId'>): {
  mode: 'full_practice' | 'subject'
  subjectKind: 'source' | 'lesson'
  subjectId: string
} {
  if (scope.lessonId) return { mode: 'subject', subjectKind: 'lesson', subjectId: scope.lessonId }
  if (scope.sourceId) return { mode: 'subject', subjectKind: 'source', subjectId: scope.sourceId }
  return { mode: 'full_practice', subjectKind: 'source', subjectId: '' }
}

export const academyRailItems: { id: AcademyPage; label: string; icon: LucideIcon; name?: string }[] = [
  { id: 'leaderboard', label: 'LDR', name: 'Leaderboard', icon: Trophy },
  { id: 'calendar', label: 'CAL', icon: CalendarDays },
  { id: 'library', label: 'LIB', icon: Library },
  { id: 'reader', label: 'RDR', icon: BookOpen },
  { id: 'discussions', label: 'DSC', icon: MessageSquare },
  { id: 'flashcards', label: 'FLC', icon: Layers },
  { id: 'quiz', label: 'QIZ', icon: HelpCircle },
  { id: 'analytics', label: 'ANL', name: 'Analytics', icon: ChartColumn },
]

// Challenge surfaces stay hidden from students until Academics opens student_access.
// Flashcards are admin-only for now, for students and observers alike.
// Scenarios stay reachable from the Library for admins, but the rail no longer lists them.
const challengeAcademyPages = new Set<AcademyPage>(['leaderboard', 'quiz', 'analytics'])
const alwaysAdminAcademyPages = new Set<AcademyPage>(['scenarios', 'flashcards'])

/** Flip cards stay hidden from students and observers after challenge pages open. */
export function showsFlashcardDeck(isAdmin: boolean): boolean {
  return isAdmin
}

export function defaultAcademyPage(isAdmin: boolean, studentAccess = false): AcademyPage {
  if (isAdmin || studentAccess) return 'leaderboard'
  return 'calendar'
}

export function academyRailForRole(isAdmin: boolean, studentAccess = false) {
  if (isAdmin) return academyRailItems
  return academyRailItems.filter((item) => {
    if (alwaysAdminAcademyPages.has(item.id)) return false
    if (challengeAcademyPages.has(item.id)) return studentAccess
    return true
  })
}

export function academyPageForRole(page: AcademyPage, isAdmin: boolean, studentAccess = false): AcademyPage {
  if (isAdmin) return page
  if (alwaysAdminAcademyPages.has(page)) return defaultAcademyPage(false, studentAccess)
  if (challengeAcademyPages.has(page) && !studentAccess) return defaultAcademyPage(false, false)
  return page
}
