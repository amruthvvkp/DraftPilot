import { type FormEvent, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Scene } from './api'
import { errorMessage, keys } from './data/queries'
import { storyApi } from './storyApi'

type SceneCreationPanelProps = { projectId: number; screenplayId?: number; afterScene?: Scene; onCreated: (sceneId: number) => void; first?: boolean }

/** Add a scene after the selected one (same act), or the draft's first scene when it has none. */
export default function SceneCreationPanel({ projectId, screenplayId, afterScene, onCreated, first = false }: SceneCreationPanelProps) {
  const queryClient = useQueryClient()
  const [heading, setHeading] = useState('INT. - DAY')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function create(event: FormEvent): Promise<void> {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const options = afterScene ? { actId: afterScene.act_id, position: afterScene.position + 1 } : { screenplayId }
      const scene = await storyApi.createScene(projectId, heading.trim() || 'INT. - DAY', options)
      await queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
      onCreated(scene.id)
    } catch (reason) {
      setError(errorMessage(reason, 'Unable to create scene'))
    } finally { setBusy(false) }
  }

  return <form className="scene-create-panel" aria-label="Create scene" onSubmit={event => void create(event)}>
    <div>
      <p className="eyebrow warm">{first ? 'FIRST SCENE' : 'NEXT SCENE'}</p>
      <input value={heading} onChange={event => setHeading(event.target.value)} aria-label="New scene heading" list="screenplay-headings" />
      <small>{afterScene ? 'Creates a new scene after the selected scene in the same act.' : 'Creates the scene at the end of the last act.'}</small>
    </div>
    <button type="submit" className={first ? 'button primary' : 'mini-button'} disabled={busy}>{first ? '＋ Create the first scene' : '＋ Add scene'}</button>
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </form>
}
