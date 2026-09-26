import type { StudyMaterial } from '../../../lib/studyMaterialApi'
import { ForgeLoader } from './ForgeLoader'
import { RunSteps } from './RunSteps'

interface GeneratingViewProps {
  material: StudyMaterial
  onBack: () => void
}

export function GeneratingView({ material, onBack }: GeneratingViewProps) {
  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Study Material · Step 3 of 4</div>
          <h2>{material.title}</h2>
        </div>
        <div className="dsn-header-actions">
          <button type="button" className="as-console__cta as-console__cta--ghost" onClick={onBack}>
            All materials
          </button>
        </div>
      </header>
      <div className="as-console__scroll">
        <div className="dsn-generating">
          <section className="as-console__panel dsn-generating__stage">
            <ForgeLoader label="Generating components and laying out the page" />
            <p className="dsn-hint">
              Diagrams and images generate first so text can be written around them. You can leave
              this tab; progress also shows in Production Operations.
            </p>
          </section>
          <section className="as-console__panel dsn-generating__steps">
            <div className="as-console__panel-head">
              <h3>Run steps</h3>
            </div>
            <div className="as-console__detail">
              <RunSteps runId={material.production_run_id} />
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
