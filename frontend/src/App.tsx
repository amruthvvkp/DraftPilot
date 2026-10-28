import { type ComponentType, lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router'
import { getWriterProfile } from './api'
import { normalizeAppearance, saveAppearance } from './theme'
import ArtifactStudio from './ArtifactStudio'
import KnowledgeGraphPage from './KnowledgeGraph'
import ProjectVault from './ProjectVault'
import ProviderSettings from './ProviderSettings'
import StoryTwinPage from './StoryTwin'
import Workspace from './Workspace'
import WritersRoom from './WritersRoom'
import CharacterDetail from './project/CharacterDetail'
import CharactersPage, { NoCharacterSelected } from './project/CharactersPage'
import ContextMapPage from './project/ContextMapPage'
import LocationsPage from './project/LocationsPage'
import OutlinePage from './project/OutlinePage'
import ProjectLayout from './project/ProjectLayout'
import StorylinePage from './project/StorylinePage'
import { useProjectId } from './project/useProjectId'

/** Render a page that takes `projectId` as a prop, remounting it when the project changes. */
function withProject(Page: ComponentType<{ projectId: number }>) {
  return function ProjectPage() {
    const projectId = useProjectId()
    return <Page key={projectId} projectId={projectId} />
  }
}

// The journey map (React Flow, dnd-kit) loads in its own chunk.
const JourneyMap = lazy(() => import('./journey/JourneyPage'))

/** The Journey map page, with a quiet fallback while its chunk loads. */
function JourneyPage() {
  return <Suspense fallback={<p className="muted">Loading the journey map…</p>}><JourneyMap /></Suspense>
}

const ScriptPage = withProject(Workspace)
const TimelinePage = withProject(({ projectId }) => <Workspace projectId={projectId} initialTimeline />)
const StudioPage = withProject(ArtifactStudio)
const GraphPage = withProject(KnowledgeGraphPage)
const RoomPage = withProject(WritersRoom)
const TwinPage = withProject(StoryTwinPage)

/** Only numeric project ids open the project shell; anything else falls back to the library. */
function ProjectGuard() {
  const { projectId } = useParams()
  return projectId && /^\d+$/.test(projectId) ? <ProjectLayout key={projectId} /> : <Navigate to="/projects" replace />
}

/** Unknown project sub-paths go to the project's script. */
function ProjectHome() {
  return <Navigate to={`/projects/${useProjectId()}`} replace />
}

/** The studio's routes. Mounted inside a router and a QueryClientProvider (see main.tsx). */
export function AppRoutes() {
  return <Routes>
    <Route path="/settings" element={<ProviderSettings />} />
    <Route path="/projects" element={<ProjectVault />} />
    <Route path="/projects/:projectId" element={<ProjectGuard />}>
      <Route index element={<ScriptPage />} />
      <Route path="script" element={<ScriptPage />} />
      <Route path="timeline" element={<TimelinePage />} />
      <Route path="storyline" element={<StorylinePage />} />
      <Route path="characters" element={<CharactersPage />}>
        <Route index element={<NoCharacterSelected />} />
        <Route path=":characterId" element={<CharacterDetail />} />
      </Route>
      <Route path="journey" element={<JourneyPage />} />
      <Route path="locations" element={<LocationsPage />} />
      <Route path="outline" element={<OutlinePage />} />
      <Route path="beats" element={<OutlinePage />} />
      <Route path="context-map" element={<ContextMapPage />} />
      <Route path="studio" element={<StudioPage />} />
      <Route path="context" element={<GraphPage />} />
      <Route path="room" element={<RoomPage />} />
      <Route path="twin" element={<TwinPage />} />
      <Route path="*" element={<ProjectHome />} />
    </Route>
    <Route path="*" element={<ProjectVault />} />
  </Routes>
}

export default function App() {
  useEffect(() => {
    getWriterProfile().then(profile => { if (profile.preferences?.appearance) saveAppearance(normalizeAppearance(profile.preferences.appearance)) }).catch(() => undefined)
  }, [])
  return <AppRoutes />
}
