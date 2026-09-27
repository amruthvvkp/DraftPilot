import { useEffect, useState } from 'react'
import { createProjectBlock, getProjectWorkspace, ProjectWorkspace } from './api'

type BlockCreationPanelProps = { projectId: number; sceneId: number }

const elementTypes = ['action', 'character', 'dialogue', 'parenthetical', 'transition', 'lyric', 'note']

export default function BlockCreationPanel({ projectId, sceneId }: BlockCreationPanelProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [elementType, setElementType] = useState('action')
  const [text, setText] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    void getProjectWorkspace(projectId).then(setWorkspace).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load block creation context'))
  }, [projectId, sceneId])

  async function create(): Promise<void> {
    const scene = workspace?.scenes.find(item => item.id === sceneId)
    if (!scene || !text.trim()) return
    try {
      await createProjectBlock(projectId, sceneId, scene.version, elementType, text.trim())
      window.location.reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create screenplay block')
    }
  }

  return <section className="block-create-panel" aria-label="Create screenplay block"><div><p className="eyebrow warm">NEW ELEMENT</p><select value={elementType} onChange={event => setElementType(event.target.value)} aria-label="New screenplay element">{elementTypes.map(item => <option key={item}>{item}</option>)}</select><textarea value={text} onChange={event => setText(event.target.value)} placeholder="Write the next semantic element…" aria-label="New element text" /></div><button className="mini-button" onClick={() => void create()} disabled={!workspace || !text.trim()}>＋ Add element</button>{error && <p className="copilot-error">{error}</p>}</section>
}
