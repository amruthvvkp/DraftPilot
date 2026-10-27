import { type FormEvent, useEffect, useState } from 'react'
import type { Act } from '../api'

type ActHeaderProps = {
  act: Act
  name: string
  canMoveEarlier: boolean
  canMoveLater: boolean
  onRename: (title: string) => void
  onMove: (delta: -1 | 1) => void
  onDelete: () => void
}

/** An act's header: rename inline, move left/right, delete. */
export function ActHeader({ act, name, canMoveEarlier, canMoveLater, onRename, onMove, onDelete }: ActHeaderProps) {
  const [title, setTitle] = useState(act.title ?? '')
  useEffect(() => setTitle(act.title ?? ''), [act.title])
  const commit = () => { if (title.trim() && title.trim() !== act.title) onRename(title.trim()); else setTitle(act.title ?? '') }
  return <div className="act-head">
    <input className="act-title-input" aria-label={`Rename ${name}`} value={title} onChange={event => setTitle(event.target.value)}
      onBlur={commit} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }} />
    <div className="beat-tools" role="group" aria-label={`Arrange ${name}`}>
      <button type="button" aria-label={`Move ${name} earlier`} disabled={!canMoveEarlier} onClick={() => onMove(-1)}>←</button>
      <button type="button" aria-label={`Move ${name} later`} disabled={!canMoveLater} onClick={() => onMove(1)}>→</button>
      <button type="button" className="danger" aria-label={`Delete ${name}`} onClick={onDelete}>×</button>
    </div>
  </div>
}

/** The "add a beat" form at the foot of a column. */
export function AddBeatForm({ columnName, onAdd }: { columnName: string; onAdd: (title: string) => Promise<void> }) {
  const [title, setTitle] = useState('')
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!title.trim()) return
    await onAdd(title.trim())
    setTitle('')
  }
  return <form className="add-beat" onSubmit={event => void submit(event)}>
    <input aria-label={`New beat in ${columnName}`} placeholder="New beat…" value={title} onChange={event => setTitle(event.target.value)} />
    <button type="submit" className="mini-button" aria-label={`Add beat to ${columnName}`} disabled={!title.trim()}>＋</button>
  </form>
}
