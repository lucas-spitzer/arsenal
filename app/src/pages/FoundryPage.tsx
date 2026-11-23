import { FoundryShell } from '../components/foundry/FoundryShell'
import { WorkspaceGate } from '../components/WorkspaceGate'
import { AtlasProvider } from '../features/atlas/AtlasProvider'
import { WorkspaceDataProvider } from '../features/workspace/WorkspaceDataProvider'
import '../foundry.css'
import '../academy.css'
import '../academy-mobile.css'
import '../design.css'

export function FoundryPage() {
  return (
    <div className="as-gallery as-gallery--full">
      <WorkspaceGate>
        <WorkspaceDataProvider>
          <AtlasProvider>
            <FoundryShell />
          </AtlasProvider>
        </WorkspaceDataProvider>
      </WorkspaceGate>
    </div>
  )
}
