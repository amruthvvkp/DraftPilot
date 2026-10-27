import { type DragEvent, type KeyboardEvent, useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { Scene } from '../api'
import type { Beat, BeatFields, Character } from '../storyApi'

export const BEAT_TYPES = ['beat', 'opening_image', 'setup', 'inciting_incident', 'plot_point', 'pinch', 'midpoint', 'crisis', 'climax', 'resolution']
export const BEAT_STATUSES = ['planned', 'drafted', 'cut']
const label = (value: string) => value.replace(/_/g, ' ')

export type BeatMoves = { earlier?: () => void; later?: () => void; previousAct?: () => void; nextAct?: () => void }

type BeatCardProps = {
  projectId: number
  beat: Beat
  scenes: Scene[]
  characters: Character[]
  moves: BeatMoves
  onSave: (fields: BeatFields) => void
  onDelete: () => void
  onCreateScene: (heading: string) => Promise<void>
  onDragStart: () => void
  onDropHere: () => void
}

/** Arrow keys on the handle move the beat: up/down within the act, left/right between acts. */
function handleKeys(moves: BeatMoves) {
  return (event: KeyboardEvent<HTMLButtonElement>) => {
    const action = { ArrowUp: moves.earlier, ArrowDown: moves.later, ArrowLeft: moves.previousAct, ArrowRight: moves.nextAct }[event.key]
    if (!action) return
    event.preventDefault()
    action()
  }
}

function toggle(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id]
}

function BeatLinks({ projectId, beat, scenes, characters, onSave, onCreateScene }: Pick<BeatCardProps, 'projectId' | 'beat' | 'scenes' | 'characters' | 'onSave' | 'onCreateScene'>) {
  const [heading, setHeading] = useState('')
  const [busy, setBusy] = useState(false)
  async function create(): Promise<void> {
    if (!heading.trim()) return
    setBusy(true)
    try { await onCreateScene(heading.trim()); setHeading('') } finally { setBusy(false) }
  }
  return <details className="beat-links">
    <summary>{beat.scene_ids.length} scenes · {beat.character_ids.length} characters</summary>
    <fieldset aria-label={`Scenes for ${beat.title}`}>
      <legend>Scenes</legend>
      {scenes.length === 0 && <small>No scenes yet.</small>}
      {scenes.map(scene => <label key={scene.id} className="check-row">
        <input type="checkbox" checked={beat.scene_ids.includes(scene.id)} onChange={() => onSave({ scene_ids: toggle(beat.scene_ids, scene.id) })} />
        <span>{scene.heading}</span>
        {beat.scene_ids.includes(scene.id) && <Link to={`/projects/${projectId}?scene=${scene.id}`} aria-label={`Open ${scene.heading} in the script`}>↗</Link>}
      </label>)}
    </fieldset>
    <div className="beat-create-scene">
      <input aria-label={`Scene heading for ${beat.title}`} placeholder="INT. PLACE - DAY" list="screenplay-headings" value={heading}
        onChange={event => setHeading(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void create() } }} />
      <button type="button" className="mini-button" disabled={!heading.trim() || busy} onClick={() => void create()}>Create scene from beat</button>
    </div>
    <fieldset aria-label={`Characters in ${beat.title}`}>
      <legend>Characters</legend>
      {characters.length === 0 && <small>No characters yet.</small>}
      {characters.map(row => <label key={row.id} className="check-row">
        <input type="checkbox" checked={beat.character_ids.includes(row.id)} onChange={() => onSave({ character_ids: toggle(beat.character_ids, row.id) })} />
        <span>{row.name}</span>
      </label>)}
    </fieldset>
  </details>
}

/** One outline beat: editable title/summary/type/status, links, moves (drag, buttons or arrow keys), delete. */
export default function BeatCard(props: BeatCardProps) {
  const { beat, moves, onSave, onDelete, onDragStart, onDropHere } = props
  const [title, setTitle] = useState(beat.title)
  const [summary, setSummary] = useState(beat.summary)
  useEffect(() => setTitle(beat.title), [beat.title])
  useEffect(() => setSummary(beat.summary), [beat.summary])
  const drop = (event: DragEvent) => { event.preventDefault(); event.stopPropagation(); onDropHere() }
  return <article className={`beat-card status-${beat.status}`} aria-label={`Beat ${beat.title}`} draggable
    onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(beat.id)); onDragStart() }}
    onDragOver={event => event.preventDefault()} onDrop={drop}>
    <div className="beat-card-head">
      <button type="button" className="beat-handle" aria-label={`Reorder ${beat.title}`} title="Drag, or use the arrow keys" onKeyDown={handleKeys(moves)}>⠿</button>
      <input aria-label="Beat title" value={title} onChange={event => setTitle(event.target.value)}
        onBlur={() => { if (title.trim() && title !== beat.title) onSave({ title: title.trim() }); else setTitle(beat.title) }} />
    </div>
    <textarea aria-label={`Summary of ${beat.title}`} rows={3} value={summary} onChange={event => setSummary(event.target.value)}
      onBlur={() => { if (summary !== beat.summary) onSave({ summary }) }} />
    <div className="beat-meta">
      <select aria-label={`Type of ${beat.title}`} value={beat.beat_type} onChange={event => onSave({ beat_type: event.target.value })}>
        {[...new Set([...BEAT_TYPES, beat.beat_type])].map(item => <option key={item} value={item}>{label(item)}</option>)}
      </select>
      <select aria-label={`Status of ${beat.title}`} value={beat.status} onChange={event => onSave({ status: event.target.value })}>
        {[...new Set([...BEAT_STATUSES, beat.status])].map(item => <option key={item} value={item}>{label(item)}</option>)}
      </select>
    </div>
    <BeatLinks {...props} />
    <div className="beat-tools" role="group" aria-label={`Move ${beat.title}`}>
      <button type="button" aria-label="Earlier" disabled={!moves.earlier} onClick={moves.earlier}>↑</button>
      <button type="button" aria-label="Later" disabled={!moves.later} onClick={moves.later}>↓</button>
      <button type="button" aria-label="Previous act" disabled={!moves.previousAct} onClick={moves.previousAct}>←</button>
      <button type="button" aria-label="Next act" disabled={!moves.nextAct} onClick={moves.nextAct}>→</button>
      <button type="button" aria-label={`Delete beat ${beat.title}`} className="danger" onClick={onDelete}>×</button>
    </div>
  </article>
}
