import type { LucideIcon } from 'lucide-react'
import {
  Anvil,
  BookText,
  Boxes,
  CircleGauge,
  Layers,
  SlidersHorizontal,
  Trophy,
} from 'lucide-react'

export type FoundryPage =
  | 'ops'
  | 'sources'
  | 'stages'
  | 'design'
  | 'challenge'
  | 'workspace'
  | 'settings'

export type FoundryView = 'grid' | 'list'

export const railIconSize = 18

export const railItems: { id: FoundryPage; label: string; icon: LucideIcon }[] = [
  { id: 'ops', label: 'OPS', icon: CircleGauge },
  { id: 'sources', label: 'SRC', icon: BookText },
  { id: 'stages', label: 'API', icon: Layers },
  { id: 'design', label: 'DSN', icon: Anvil },
  { id: 'challenge', label: 'CHL', icon: Trophy },
  { id: 'workspace', label: 'WRK', icon: Boxes },
  { id: 'settings', label: 'CFG', icon: SlidersHorizontal },
]
