import { FoundryShell } from '../components/foundry/FoundryShell'
import { WorkspaceGate } from '../components/WorkspaceGate'
import { WorkspaceDataProvider } from '../features/workspace/WorkspaceDataProvider'
import '../foundry.css'
import '../academy.css'
import '../design.css'

export function FoundryPage() {
  return (
    <div className="as-gallery as-gallery--full">
      <WorkspaceGate>
        <WorkspaceDataProvider>
          <FoundryShell />
        </WorkspaceDataProvider>
      </WorkspaceGate>
    </div>
  )
}
