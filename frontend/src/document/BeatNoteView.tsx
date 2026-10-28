import { useEffect, useRef, useState } from 'react'
import { NodeViewWrapper, type ReactNodeViewProps } from '@tiptap/react'

export type BeatActions = {
  /** Save a beat's title and summary (with If-Match); resolves false when it failed. */
  saveBeat: (beatId: number, fields: { title: string; summary: string }) => Promise<boolean>
  /** Create a scene for a beat that has none and link it. */
  createScene: (beatId: number) => Promise<void>
}

/** A beat from the outline, inline above its scenes: editable, collapsible, not part of the script. */
export default function BeatNoteView({ node, extension }: ReactNodeViewProps) {
  const actions = (extension.options as { beatActions: { current: BeatActions } }).beatActions
  const beatId = Number(node.attrs.beat_id)
  const [title, setTitle] = useState(String(node.attrs.title))
  const [summary, setSummary] = useState(String(node.attrs.summary))
  const [open, setOpen] = useState(Boolean(node.attrs.summary) || !node.attrs.linked)
  const [state, setState] = useState<'idle' | 'saving' | 'error'>('idle')
  const editing = useRef(false)

  // Follow the server's text, but never under the writer's cursor.
  useEffect(() => { if (!editing.current) { setTitle(String(node.attrs.title)); setSummary(String(node.attrs.summary)) } }, [node.attrs.title, node.attrs.summary, node.attrs.version])

  async function save(): Promise<void> {
    editing.current = false
    if (title === node.attrs.title && summary === node.attrs.summary) return
    if (!title.trim()) { setTitle(String(node.attrs.title)); return }
    setState('saving')
    setState(await actions.current.saveBeat(beatId, { title: title.trim(), summary }) ? 'idle' : 'error')
  }

  return <NodeViewWrapper as="aside" className={`beat-note outline-only${node.attrs.linked ? '' : ' unlinked'}`} contentEditable={false} role="group" aria-label={`Beat: ${node.attrs.title}`} data-beat-id={beatId}>
    <div className="beat-note-head">
      <button type="button" className="beat-toggle" aria-expanded={open} aria-label={open ? 'Collapse beat' : 'Expand beat'} onClick={() => setOpen(value => !value)}>{open ? '▾' : '▸'}</button>
      <span className="eyebrow warm">BEAT</span>
      <input className="beat-title" aria-label="Beat title" value={title} onFocus={() => { editing.current = true }} onChange={event => setTitle(event.target.value)} onBlur={() => void save()}
        onKeyDown={event => { if (event.key === 'Enter') (event.target as HTMLInputElement).blur() }} />
      {state === 'saving' && <small>Saving…</small>}
      {state === 'error' && <small role="alert">Not saved</small>}
    </div>
    {open && <textarea className="beat-summary" aria-label="Beat summary" placeholder="What happens in this beat…" value={summary} rows={2}
      onFocus={() => { editing.current = true }} onChange={event => setSummary(event.target.value)} onBlur={() => void save()} />}
    {!node.attrs.linked && <div className="beat-placeholder">
      <span>No scene written for this beat yet.</span>
      <button type="button" className="button quiet" onClick={() => void actions.current.createScene(beatId)}>Create scene from beat</button>
    </div>}
  </NodeViewWrapper>
}
