import { type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Act } from '../api'
import { errorMessage, keys, useBeats, useWorkspace } from '../data/queries'
import { type Beat, storyApi } from '../storyApi'
import { beatsIn, planBeatMove } from '../project/outlinePlan'
import { useProjectId } from '../project/useProjectId'
import { ToolHead } from './VisualsLayout'

const actName = (act: Act) => act.title || `Act ${act.position + 1}`
const label = (type: string) => type.replace(/_/g, ' ')

type Column = { id: number | null; name: string; beats: Beat[] }

/** Index cards over the outline's beats, one column per act. Arrow keys (or the card buttons) move a focused card. */
export default function CorkboardPage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const { data: workspace } = useWorkspace(projectId)
  const { data: beatList, error: loadError } = useBeats(projectId)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const refocus = useRef<number | null>(null)
  const cards = useRef(new Map<number, HTMLElement>())
  const writes = useRef<Promise<unknown>>(Promise.resolve())

  const acts = [...(workspace?.acts ?? [])].sort((a, b) => a.position - b.position)
  const actIds = new Set(acts.map(act => act.id))
  const beats = beatList ?? []
  const unassigned = beatsIn(beats, null, actIds)
  const columns: Column[] = [
    ...acts.map(act => ({ id: act.id, name: actName(act), beats: beatsIn(beats, act.id, actIds) })),
    ...(unassigned.length ? [{ id: null, name: 'Unassigned', beats: unassigned }] : []),
  ]

  // Keep keyboard focus on the card that just moved, wherever it re-renders.
  useEffect(() => {
    if (refocus.current === null) return
    const element = cards.current.get(refocus.current)
    if (element) { element.focus(); refocus.current = null }
  })

  function move(beat: Beat, columnIndex: number, index: number): void {
    const column = columns[columnIndex]
    if (!column) return
    const target = Math.max(0, Math.min(index, column.beats.filter(item => item.id !== beat.id).length))
    // Show the move at once, then save it as versioned beat PATCHes, one at a time.
    const current = queryClient.getQueryData<Beat[]>(keys.beats(projectId)) ?? beats
    const changes = planBeatMove(current, beat.id, column.id, target, actIds)
    if (!changes.length) return
    queryClient.setQueryData<Beat[]>(keys.beats(projectId), rows => rows?.map(row => {
      const change = changes.find(item => item.beat.id === row.id)
      return change ? { ...row, ...change.fields } : row
    }))
    refocus.current = beat.id
    setStatus(`Moved ${beat.title} to position ${target + 1} in ${column.name}`)
    setError('')
    const save = writes.current.then(async () => {
      for (const change of changes) {
        const latest = queryClient.getQueryData<Beat[]>(keys.beats(projectId))?.find(row => row.id === change.beat.id)
        const saved = await storyApi.updateBeat(projectId, { ...change.beat, version: latest?.version ?? change.beat.version }, change.fields)
        queryClient.setQueryData<Beat[]>(keys.beats(projectId), rows => rows?.map(row => row.id === saved.id ? { ...row, version: saved.version } : row))
      }
    }).catch(reason => setError(errorMessage(reason, 'Unable to move the card')))
      .finally(() => queryClient.invalidateQueries({ queryKey: keys.beats(projectId) }))
    writes.current = save
  }

  function onKey(event: KeyboardEvent, beat: Beat, columnIndex: number, index: number): void {
    if (event.target !== event.currentTarget) return
    const moves: Record<string, () => void> = {
      ArrowUp: () => move(beat, columnIndex, index - 1),
      ArrowDown: () => move(beat, columnIndex, index + 1),
      ArrowLeft: () => move(beat, columnIndex - 1, columns[columnIndex - 1]?.beats.length ?? 0),
      ArrowRight: () => move(beat, columnIndex + 1, columns[columnIndex + 1]?.beats.length ?? 0),
    }
    const action = moves[event.key]
    if (!action) return
    event.preventDefault()
    action()
  }

  return <>
    <ToolHead title="Corkboard">Your outline’s beats as index cards, one column per act. Focus a card and use the arrow keys (up and down within an act, left and right between acts), or its buttons. Every move is saved to the outline.</ToolHead>
    {(error || loadError) && <p className="notice" role="alert">{error || errorMessage(loadError, 'Unable to load the beats')}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    <p className="visually-hidden" role="status" aria-live="polite">{status}</p>
    {beatList && !beats.length && <p className="empty-copy">No beats yet. Add some on the Outline, or lay a structure template over it.</p>}
    <div className="corkboard" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(200px, 1fr))` }}>
      {columns.map((column, columnIndex) => <section key={column.id ?? 'unassigned'} className="cork-column" aria-label={column.name}>
        <h2 className="eyebrow">{column.name} <small>{column.beats.length}</small></h2>
        <ol>
          {column.beats.map((beat, index) => <li key={beat.id}>
            <article className={`index-card ${beat.status}`} tabIndex={0} aria-label={`${beat.title}, card ${index + 1} of ${column.beats.length} in ${column.name}`}
              aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight" ref={element => { if (element) cards.current.set(beat.id, element); else cards.current.delete(beat.id) }}
              onKeyDown={event => onKey(event, beat, columnIndex, index)}>
              <header>{beat.beat_type !== 'beat' && <span className="card-type">{label(beat.beat_type)}</span>}<span className="card-status">{beat.status}</span></header>
              <h3>{beat.title}</h3>
              {beat.summary && <p>{beat.summary}</p>}
              <footer>
                <small>{beat.scene_ids.length} scene{beat.scene_ids.length === 1 ? '' : 's'}</small>
                <span role="group" aria-label={`Move ${beat.title}`}>
                  <button type="button" aria-label="Earlier" disabled={index === 0} onClick={() => move(beat, columnIndex, index - 1)}>↑</button>
                  <button type="button" aria-label="Later" disabled={index === column.beats.length - 1} onClick={() => move(beat, columnIndex, index + 1)}>↓</button>
                  <button type="button" aria-label="Previous act" disabled={columnIndex === 0} onClick={() => move(beat, columnIndex - 1, columns[columnIndex - 1]?.beats.length ?? 0)}>←</button>
                  <button type="button" aria-label="Next act" disabled={columnIndex === columns.length - 1} onClick={() => move(beat, columnIndex + 1, columns[columnIndex + 1]?.beats.length ?? 0)}>→</button>
                </span>
              </footer>
            </article>
          </li>)}
        </ol>
      </section>)}
    </div>
  </>
}
