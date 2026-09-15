import type { LucideIcon } from 'lucide-react'
import {
  BookText,
  Boxes,
  Brain,
  CircleGauge,
  Layers,
  Package,
  SlidersHorizontal,
} from 'lucide-react'

export type FoundryPage =
  | 'ops'
  | 'sources'
  | 'stages'
  | 'artifacts'
  | 'assessments'
  | 'workspace'
  | 'settings'

export type FoundryView = 'grid' | 'list'

export const railIconSize = 18

export const railItems: { id: FoundryPage; label: string; icon: LucideIcon }[] = [
  { id: 'ops', label: 'OPS', icon: CircleGauge },
  { id: 'sources', label: 'SRC', icon: BookText },
  { id: 'stages', label: 'API', icon: Layers },
  { id: 'artifacts', label: 'ART', icon: Package },
  { id: 'assessments', label: 'ASM', icon: Brain },
  { id: 'workspace', label: 'WRK', icon: Boxes },
  { id: 'settings', label: 'CFG', icon: SlidersHorizontal },
]
