import { apiRequest, apiRequestText, apiRequestVoid, apiUrl } from './apiClient'
import { uploadMultipart } from './workspaceApi'

export type ComponentType = 'text' | 'diagram' | 'image'
export type ImageProvider = 'openai' | 'google'
export type StudyMaterialStatus =
  | 'configuring'
  | 'generating'
  | 'draft'
  | 'finalizing'
  | 'finalized'
  | 'failed'

export interface SectionBox {
  x: number
  y: number
  w: number
  h: number
}

interface SectionBase {
  id: string
  label: string
  box: SectionBox
  size_in: [number, number]
}

export interface FlexibleSection extends SectionBase {
  kind: 'flexible'
  allowed_types: ComponentType[]
  max_components: number
}

export interface StrictSection extends SectionBase {
  kind: 'strict'
  content: 'title' | 'logo' | 'footer'
  max_words: number | null
}

export type TemplateSection = FlexibleSection | StrictSection

export interface StudyTemplate {
  id: string
  name: string
  description: string
  orientation: 'portrait' | 'landscape'
  page: { size: string; width_in: number; height_in: number; margin_in: number }
  disclaimer: 'footer' | 'per_section'
  cut_lines: boolean
  has_logo_section: boolean
  sections: TemplateSection[]
}

export interface ThemeLogo {
  id: string
  label: string
  variant: 'light' | 'dark'
  aspect: number
  asset: string
}

export interface StudyTheme {
  id: string
  name: string
  description: string
  source_url: string | null
  colors: Record<string, string>
  disclaimer: string | null
  default_logo_id: string | null
  logos: ThemeLogo[]
}

export interface ImageCatalog {
  default_provider: ImageProvider
  providers: ImageProvider[]
  models: Record<ImageProvider, string[]>
  default_models: Record<ImageProvider, string>
  aspect_ratios: string[]
  qualities: string[]
  image_sizes: string[]
}

export interface StudyCatalog {
  themes: StudyTheme[]
  templates: StudyTemplate[]
  image: ImageCatalog
  limits: { max_file_bytes: number; max_files_per_component: number }
}

export interface StudyMaterialOptions {
  logo_locked: boolean
  logo_id: string | null
  footer_text: string
  section_notes: Record<string, string>
}

export interface ImageSettings {
  provider: ImageProvider
  model: string
  aspect_ratio: string
  quality: string
  image_size: string
}

export interface ComponentFile {
  id: string
  filename: string
  mime_type: string
  file_size_bytes: number
}

export interface ComponentVersion {
  id: string
  version: number
  output: Record<string, unknown>
  output_path: string | null
  instructions: string
  model: string | null
  provider: string | null
  settings: Record<string, unknown>
  theme_id: string
  created_at: string
}

export interface StudyComponent {
  id: string
  section_id: string
  component_type: ComponentType
  position: number
  instructions: string
  settings: Partial<ImageSettings>
  files: ComponentFile[]
  active_version_id: string | null
  active_version: ComponentVersion | null
  version_count: number
  created_at: string
  updated_at: string
}

export interface ValidationIssue {
  code: string
  message: string
  section_id?: string
  component_id?: string
}

export interface StudyMaterial {
  id: string
  workspace_id: string
  title: string
  slug: string
  theme_id: string
  template_id: string
  options: StudyMaterialOptions
  status: StudyMaterialStatus
  layout: Record<string, unknown>
  validation: { stage?: 'draft' | 'finalize'; checked_at?: string; issues?: ValidationIssue[] }
  production_run_id: string | null
  artifact_id: string | null
  error: string | null
  created_at: string
  updated_at: string
  finalized_at: string | null
  component_count: number
  components: StudyComponent[]
}

export const COMPONENT_TYPE_LABELS: Record<ComponentType, string> = {
  text: 'Text',
  diagram: 'Diagram',
  image: 'Image',
}

export function catalogAssetUrl(asset: string): string {
  return apiUrl(`/study-material/assets/${asset}`)
}

export async function getStudyCatalog(): Promise<StudyCatalog> {
  return apiRequest<StudyCatalog>('/study-material/catalog')
}

export async function listStudyMaterials(workspaceId: string): Promise<StudyMaterial[]> {
  return apiRequest<StudyMaterial[]>(`/workspaces/${workspaceId}/study-materials`)
}

export async function createStudyMaterial(
  workspaceId: string,
  payload: { title: string; theme_id: string; template_id: string; options: StudyMaterialOptions },
): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/workspaces/${workspaceId}/study-materials`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getStudyMaterial(materialId: string): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/study-materials/${materialId}`)
}

export async function updateStudyMaterial(
  materialId: string,
  payload: { title?: string; options?: StudyMaterialOptions },
): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/study-materials/${materialId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteStudyMaterial(materialId: string): Promise<void> {
  return apiRequestVoid(`/study-materials/${materialId}`, { method: 'DELETE' })
}

export async function createComponent(
  materialId: string,
  payload: { section_id: string; component_type: ComponentType; instructions?: string },
): Promise<StudyComponent> {
  return apiRequest<StudyComponent>(`/study-materials/${materialId}/components`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateComponent(
  materialId: string,
  componentId: string,
  payload: { instructions?: string; settings?: Partial<ImageSettings> },
): Promise<StudyComponent> {
  return apiRequest<StudyComponent>(`/study-materials/${materialId}/components/${componentId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteComponent(materialId: string, componentId: string): Promise<void> {
  return apiRequestVoid(`/study-materials/${materialId}/components/${componentId}`, {
    method: 'DELETE',
  })
}

export async function uploadComponentFile(
  materialId: string,
  componentId: string,
  file: File,
): Promise<StudyComponent> {
  return uploadMultipart<StudyComponent>(
    `/study-materials/${materialId}/components/${componentId}/files`,
    file,
  )
}

export async function deleteComponentFile(
  materialId: string,
  componentId: string,
  fileId: string,
): Promise<StudyComponent> {
  return apiRequest<StudyComponent>(
    `/study-materials/${materialId}/components/${componentId}/files/${fileId}`,
    { method: 'DELETE' },
  )
}

export async function generateStudyMaterial(materialId: string): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/study-materials/${materialId}/generate`, { method: 'POST' })
}

export async function finalizeStudyMaterial(materialId: string): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/study-materials/${materialId}/finalize`, { method: 'POST' })
}

export async function reopenStudyMaterial(materialId: string): Promise<StudyMaterial> {
  return apiRequest<StudyMaterial>(`/study-materials/${materialId}/reopen`, { method: 'POST' })
}

export async function getDraftHtml(materialId: string): Promise<string> {
  return apiRequestText(`/study-materials/${materialId}/draft`)
}
