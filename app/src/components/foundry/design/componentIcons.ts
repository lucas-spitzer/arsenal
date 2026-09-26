import { FileText, Image as ImageIcon, Workflow } from 'lucide-react'
import type { ComponentType } from '../../../lib/studyMaterialApi'

export const COMPONENT_ICONS: Record<ComponentType, typeof FileText> = {
  text: FileText,
  diagram: Workflow,
  image: ImageIcon,
}
