import type { LucideIcon } from 'lucide-react'
import { BookOpen, HelpCircle, Layers, Library, Lightbulb, MessageSquare } from 'lucide-react'

export type AcademyPage =
  | 'library'
  | 'reader'
  | 'wiki'
  | 'flashcards'
  | 'quiz'
  | 'scenarios'
  | 'discussions'

// Scope passed when opening a runner from the Library (filter + focus target).
export type AcademyScope = { sourceId: string | null; targetId: string | null }

export const emptyAcademyScope: AcademyScope = { sourceId: null, targetId: null }

export const academyRailItems: { id: AcademyPage; label: string; icon: LucideIcon }[] = [
  { id: 'library', label: 'LIB', icon: Library },
  { id: 'reader', label: 'RDR', icon: BookOpen },
  { id: 'discussions', label: 'DSC', icon: MessageSquare },
  { id: 'flashcards', label: 'FLC', icon: Layers },
  { id: 'quiz', label: 'QIZ', icon: HelpCircle },
  { id: 'scenarios', label: 'SCN', icon: Lightbulb },
]
