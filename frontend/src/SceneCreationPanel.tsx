import { useEffect, useState } from 'react'
import { createProjectScene, getProjectWorkspace, ProjectWorkspace } from './api'

type SceneCreationPanelProps = { projectId: number; sceneId: number }

export default function SceneCreationPanel({ projectId, sceneId }: SceneCreationPanelProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [heading, setHeading] = useState('INT. - DAY')
  const [error, setError] = useState('')

  useEffect(() => {
    void getProjectWorkspace(projectId).then(setWorkspace).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load scene creation context'))
  }, [projectId, sceneId])

  async function create(): Promise<void> {
    const scene = workspace?.scenes.find(item => item.id === sceneId)
    if (!workspace?.screenplay || !scene) return
    try {
      await createProjectScene(projectId, workspace.screenplay.id, scene.act_id, heading.trim() || 'INT. - DAY', scene.position + 1)
      window.location.reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create scene')
    }
  }

  return <section className="scene-create-panel" aria-label="Create scene"><div><p className="eyebrow warm">NEXT SCENE</p><input value={heading} onChange={event => setHeading(event.target.value)} aria-label="New scene heading" list="screenplay-headings" /><small>Creates a new scene after the selected scene in the same act.</small></div><button className="mini-button" onClick={() => void create()} disabled={!workspace}>＋ Add scene</button>{error && <p className="copilot-error">{error}</p>}</section>
}
