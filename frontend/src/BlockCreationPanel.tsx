import { type FormEvent, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createProjectBlock, type Scene } from './api'
import { errorMessage, keys } from './data/queries'

type BlockCreationPanelProps = { projectId: number; scene: Scene }

const elementTypes = ['action', 'character', 'dialogue', 'parenthetical', 'transition', 'lyric', 'note']

/** Append a typed screenplay element to a scene. */
export default function BlockCreationPanel({ projectId, scene }: BlockCreationPanelProps) {
  const queryClient = useQueryClient()
  const [elementType, setElementType] = useState('action')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function create(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!text.trim()) return
    setBusy(true); setError('')
    try {
      await createProjectBlock(projectId, scene.id, scene.version, elementType, text.trim())
      setText('')
      await queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
    } catch (reason) {
      setError(errorMessage(reason, 'Unable to create screenplay block'))
      void queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
    } finally { setBusy(false) }
  }

  return <form className="block-create-panel" aria-label="Create screenplay block" onSubmit={event => void create(event)}>
    <div>
      <p className="eyebrow warm">NEW ELEMENT</p>
      <select value={elementType} onChange={event => setElementType(event.target.value)} aria-label="New screenplay element">{elementTypes.map(item => <option key={item}>{item}</option>)}</select>
      <textarea value={text} onChange={event => setText(event.target.value)} placeholder="Write the next semantic element…" aria-label="New element text"
        onKeyDown={event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void create(event) }} />
    </div>
    <button type="submit" className="mini-button" disabled={busy || !text.trim()}>＋ Add element</button>
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </form>
}
