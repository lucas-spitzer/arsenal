import { useCallback, useEffect, useState } from 'react'
import { useWorkspace } from '../../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../../features/workspace/workspaceDataContext'
import {
  deleteStudyMaterial,
  finalizeStudyMaterial,
  generateStudyMaterial,
  getStudyCatalog,
  getStudyMaterial,
  listStudyMaterials,
  reopenStudyMaterial,
  type StudyCatalog,
  type StudyMaterial,
} from '../../../lib/studyMaterialApi'
import { ErrorBanner } from '../ErrorBanner'
import { FoundryDialog } from '../FoundryDialog'
import { FoundryLoader } from '../FoundryLoader'
import { ConfigureStep } from './ConfigureStep'
import { DraftView } from './DraftView'
import { GeneratingView } from './GeneratingView'
import { SetupStep } from './SetupStep'
import { KnowledgeWorkshop } from './KnowledgeWorkshop'
import { StudyMaterialList } from './StudyMaterialList'

type DesignView = { kind: 'list' } | { kind: 'setup' } | { kind: 'material'; id: string }

const POLL_MS = 3000

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

export function FoundryDesign() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const [catalog, setCatalog] = useState<StudyCatalog | null>(null)
  const [materials, setMaterials] = useState<StudyMaterial[] | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<DesignView>({ kind: 'list' })
  const [product, setProduct] = useState<'study' | 'knowledge'>('study')

  useEffect(() => {
    getStudyCatalog()
      .then(setCatalog)
      .catch((caught: unknown) => setError(errorMessage(caught, 'Could not load themes and templates.')))
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    listStudyMaterials(workspaceId)
      .then((rows) => {
        if (!cancelled) setMaterials(rows)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught, 'Could not load study material.'))
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, reloadKey])

  const backToList = () => {
    setView({ kind: 'list' })
    setReloadKey((key) => key + 1)
  }

  if (product === 'knowledge' && view.kind === 'list') {
    return <KnowledgeWorkshop onShowStudy={() => setProduct('study')} />
  }

  if (!catalog) {
    return (
      <>
        <header className="as-console__header">
          <div>
            <div className="as-console__eyebrow">Study material</div>
            <h2>Design Forge</h2>
          </div>
        </header>
        <div className="as-console__scroll">
          {error ? <ErrorBanner message={error} /> : <FoundryLoader label="Loading themes and templates" size="sm" />}
        </div>
      </>
    )
  }

  if (view.kind === 'setup') {
    return (
      <SetupStep
        catalog={catalog}
        onCancel={() => setView({ kind: 'list' })}
        onCreated={(material) => {
          setMaterials((current) => [material, ...(current ?? [])])
          setView({ kind: 'material', id: material.id })
        }}
      />
    )
  }

  if (view.kind === 'material') {
    return <MaterialWorkspace key={view.id} materialId={view.id} catalog={catalog} onBack={backToList} />
  }

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Study material</div>
          <h2>Design Forge</h2>
        </div>
        <div className="kproj-switch" role="tablist" aria-label="Forge Knowledge">
          <button type="button" role="tab" aria-selected className="is-active">
            Study material
          </button>
          <button type="button" role="tab" aria-selected={false} onClick={() => setProduct('knowledge')}>
            Knowledge
          </button>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta" onClick={() => setView({ kind: 'setup' })}>
            + New study material
          </button>
        </div>
      </header>
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
        <StudyMaterialList
          catalog={catalog}
          materials={materials ?? []}
          isLoading={materials === null}
          onOpen={(id) => setView({ kind: 'material', id })}
          onCreate={() => setView({ kind: 'setup' })}
        />
      </div>
    </>
  )
}

function MaterialWorkspace({
  materialId,
  catalog,
  onBack,
}: {
  materialId: string
  catalog: StudyCatalog
  onBack: () => void
}) {
  const { refresh, downloadArtifact } = useWorkspaceData()
  const [material, setMaterial] = useState<StudyMaterial | null>(null)
  const [editing, setEditing] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const status = material?.status

  const reload = useCallback(() => {
    getStudyMaterial(materialId)
      .then(setMaterial)
      .catch((caught: unknown) => setError(errorMessage(caught, 'Could not load the study material.')))
  }, [materialId])

  useEffect(reload, [reload])

  useEffect(() => {
    if (status !== 'generating' && status !== 'finalizing') return
    const intervalId = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(intervalId)
  }, [status, reload])

  useEffect(() => {
    if (status === 'draft' || status === 'finalized' || status === 'failed') void refresh()
  }, [status, refresh])

  const act = async (task: () => Promise<StudyMaterial>, fallback: string) => {
    setIsBusy(true)
    setError(null)
    try {
      setMaterial(await task())
      await refresh()
    } catch (caught) {
      setError(errorMessage(caught, fallback))
    } finally {
      setIsBusy(false)
    }
  }

  if (!material) {
    return (
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : <FoundryLoader label="Loading" size="sm" />}
      </div>
    )
  }

  const template = catalog.templates.find((item) => item.id === material.template_id)
  const theme = catalog.themes.find((item) => item.id === material.theme_id)
  if (!template || !theme) {
    return (
      <div className="as-console__scroll">
        <ErrorBanner message="This material uses a theme or template that no longer exists." />
      </div>
    )
  }

  const confirmDelete = () => {
    if (isDeleting) return
    setIsDeleting(true)
    setError(null)
    void deleteStudyMaterial(material.id)
      .then(onBack)
      .catch((caught: unknown) => {
        setError(errorMessage(caught, 'Could not delete.'))
        setIsDeleting(false)
        setDeleteOpen(false)
      })
  }

  const errorBanner = error ? (
    <div className="dsn-float-error">
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
    </div>
  ) : null

  if (material.status === 'generating') {
    return (
      <>
        {errorBanner}
        <GeneratingView material={material} onBack={onBack} />
      </>
    )
  }

  const configuring =
    material.status === 'configuring' || material.status === 'failed' || (material.status === 'draft' && editing)

  if (configuring) {
    return (
      <>
        {errorBanner}
        <ConfigureStep
          material={material}
          catalog={catalog}
          template={template}
          theme={theme}
          isStarting={isBusy}
          onMaterialChange={setMaterial}
          onBack={onBack}
          onDelete={() => setDeleteOpen(true)}
          onGenerate={() => {
            setEditing(false)
            void act(() => generateStudyMaterial(material.id), 'Could not start generation.')
          }}
        />
        <FoundryDialog
          title="Delete study material"
          open={deleteOpen}
          onClose={() => {
            if (!isDeleting) setDeleteOpen(false)
          }}
        >
          <p className="as-console__confirm-copy">
            Delete "{material.title}"? Finalized PDFs stay in the Library.
          </p>
          <div className="as-console__dialog-actions">
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              onClick={() => setDeleteOpen(false)}
              disabled={isDeleting}
              autoFocus
            >
              Cancel
            </button>
            <button type="button" className="as-console__cta" onClick={confirmDelete} disabled={isDeleting}>
              {isDeleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </FoundryDialog>
      </>
    )
  }

  return (
    <>
      {errorBanner}
      <DraftView
        material={material}
        template={template}
        theme={theme}
        isBusy={isBusy}
        onBack={onBack}
        onEdit={() => setEditing(true)}
        onFinalize={() => void act(() => finalizeStudyMaterial(material.id), 'Could not start finalization.')}
        onReopen={() => void act(() => reopenStudyMaterial(material.id), 'Could not reopen.')}
        onDownload={() => {
          if (!material.artifact_id) return
          void downloadArtifact(material.artifact_id).catch((caught: unknown) =>
            setError(errorMessage(caught, 'Download failed.')),
          )
        }}
      />
    </>
  )
}
