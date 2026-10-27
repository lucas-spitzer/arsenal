import type { LucideIcon } from 'lucide-react'
import {
  Anvil,
  BookText,
  Boxes,
  CalendarDays,
  CircleGauge,
  Layers,
  SlidersHorizontal,
  Target,
} from 'lucide-react'

export type FoundryPage =
  | 'ops'
  | 'sources'
  | 'stages'
  | 'design'
  | 'calendar'
  | 'objectives'
  | 'workspace'
  | 'settings'

export type FoundryView = 'grid' | 'list'

export const railIconSize = 18

export const railItems: { id: FoundryPage; label: string; icon: LucideIcon }[] = [
  { id: 'ops', label: 'OPS', icon: CircleGauge },
  { id: 'sources', label: 'SRC', icon: BookText },
  { id: 'stages', label: 'API', icon: Layers },
  { id: 'design', label: 'DSN', icon: Anvil },
  { id: 'calendar', label: 'CAL', icon: CalendarDays },
  { id: 'objectives', label: 'ELO', icon: Target },
  { id: 'workspace', label: 'WRK', icon: Boxes },
  { id: 'settings', label: 'CFG', icon: SlidersHorizontal },
]
