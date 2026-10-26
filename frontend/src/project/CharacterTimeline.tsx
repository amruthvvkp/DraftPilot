import { type FormEvent, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { errorMessage, keys, useBeats, useTimeline, useWorkspace } from '../data/queries'
import { type Character, storyApi, type TimelineEvent, type TimelineEventFields } from '../storyApi'
import ConfirmDialog from './ConfirmDialog'
import { byPosition, moveItem, persistPositions } from './order'

type EventForm = { title: string; story_time: string; objective: string; emotional_state: string; description: string; scene_id: string; beat_id: string }
const EMPTY: EventForm = { title: '', story_time: '', objective: '', emotional_state: '', description: '', scene_id: '', beat_id: '' }

function formOf(row: TimelineEvent): EventForm {
  return { title: row.title, story_time: row.story_time, objective: row.objective, emotional_state: row.emotional_state, description: row.description, scene_id: row.scene_id ? String(row.scene_id) : '', beat_id: row.beat_id ? String(row.beat_id) : '' }
}

function fieldsOf(form: EventForm): TimelineEventFields {
  return {
    title: form.title.trim(), story_time: form.story_time.trim(), objective: form.objective, emotional_state: form.emotional_state, description: form.description,
    scene_id: form.scene_id ? Number(form.scene_id) : null, beat_id: form.beat_id ? Number(form.beat_id) : null,
  }
}

type Option = { id: number; label: string }

function EventFields({ form, onChange, scenes, beats, idPrefix }: { form: EventForm; onChange: (form: EventForm) => void; scenes: Option[]; beats: Option[]; idPrefix: string }) {
  const set = (name: keyof EventForm) => (value: string) => onChange({ ...form, [name]: value })
  return <div className="event-fields">
    <label>Event<input id={`${idPrefix}-title`} value={form.title} onChange={event => set('title')(event.target.value)} /></label>
    <label>Story time<input value={form.story_time} placeholder="e.g. Day 3, night" onChange={event => set('story_time')(event.target.value)} /></label>
    <label>Objective here<input value={form.objective} onChange={event => set('objective')(event.target.value)} /></label>
    <label>Emotional state<input value={form.emotional_state} onChange={event => set('emotional_state')(event.target.value)} /></label>
    <label className="wide">What happens<textarea rows={2} value={form.description} onChange={event => set('description')(event.target.value)} /></label>
    <label>Scene<select value={form.scene_id} onChange={event => set('scene_id')(event.target.value)}>
      <option value="">No scene</option>{scenes.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
    </select></label>
    <label>Beat<select value={form.beat_id} onChange={event => set('beat_id')(event.target.value)}>
      <option value="">No beat</option>{beats.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
    </select></label>
  </div>
}

type RowProps = { row: TimelineEvent; index: number; count: number; scenes: Option[]; beats: Option[]; onMove: (delta: -1 | 1) => void; onSave: (fields: TimelineEventFields) => Promise<boolean>; onDelete: () => void }

function EventRow({ row, index, count, scenes, beats, onMove, onSave, onDelete }: RowProps) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<EventForm>(() => formOf(row))
  const scene = scenes.find(item => item.id === row.scene_id)
  const beat = beats.find(item => item.id === row.beat_id)
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (form.title.trim() && await onSave(fieldsOf(form))) setEditing(false)
  }
  return <li className="timeline-event">
    <span className="timeline-event-index" aria-hidden="true">{index + 1}</span>
    {editing ? <form aria-label={`Edit ${row.title}`} onSubmit={event => void submit(event)}>
      <EventFields form={form} onChange={setForm} scenes={scenes} beats={beats} idPrefix={`event-${row.id}`} />
      <div className="story-actions"><button className="button primary" type="submit" disabled={!form.title.trim()}>Save event</button><button className="button quiet" type="button" onClick={() => { setForm(formOf(row)); setEditing(false) }}>Cancel</button></div>
    </form> : <div className="timeline-event-body">
      <strong>{row.title}</strong>{row.story_time && <small> · {row.story_time}</small>}
      {row.objective && <p><em>Wants:</em> {row.objective}</p>}
      {row.emotional_state && <p><em>Feels:</em> {row.emotional_state}</p>}
      {row.description && <p>{row.description}</p>}
      {(scene || beat) && <small>{scene ? `Scene: ${scene.label}` : ''}{scene && beat ? ' · ' : ''}{beat ? `Beat: ${beat.label}` : ''}</small>}
    </div>}
    {!editing && <div className="beat-tools" role="group" aria-label={`Arrange ${row.title}`}>
      <button type="button" aria-label={`Move ${row.title} earlier`} disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
      <button type="button" aria-label={`Move ${row.title} later`} disabled={index === count - 1} onClick={() => onMove(1)}>↓</button>
      <button type="button" aria-label={`Edit ${row.title}`} onClick={() => { setForm(formOf(row)); setEditing(true) }}>✎</button>
      <button type="button" className="danger" aria-label={`Delete ${row.title}`} onClick={onDelete}>×</button>
    </div>}
  </li>
}

/** A character's own timeline: ordered events with objective, emotional state and an optional scene or beat. */
export default function CharacterTimeline({ projectId, character }: { projectId: number; character: Character }) {
  const queryClient = useQueryClient()
  const { data: events } = useTimeline(projectId, character.id)
  const scenes: Option[] = (useWorkspace(projectId).data?.scenes ?? []).map(scene => ({ id: scene.id, label: scene.heading }))
  const beats: Option[] = (useBeats(projectId).data ?? []).map(beat => ({ id: beat.id, label: beat.title }))
  const [form, setForm] = useState<EventForm>(EMPTY)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState<TimelineEvent | null>(null)
  const ordered = byPosition(events ?? [])
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.timelines(projectId) })

  async function run(change: () => Promise<unknown>, fallback: string): Promise<boolean> {
    setError('')
    try { await change(); return true } catch (reason) { setError(errorMessage(reason, fallback)); return false } finally { await refresh() }
  }

  async function add(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!form.title.trim()) return
    const ok = await run(() => storyApi.createEvent(projectId, { ...fieldsOf(form), character_id: character.id, title: form.title.trim(), position: ordered.length }), 'Unable to add the event')
    if (ok) setForm(EMPTY)
  }

  function move(index: number, delta: -1 | 1): void {
    const next = moveItem(ordered, index, index + delta)
    void run(() => persistPositions(next, (row, position) => storyApi.updateEvent(projectId, row, { position })), 'Unable to reorder the timeline')
  }

  return <section className="story-subsection" aria-label={`${character.name} timeline`}>
    <h3>Timeline</h3>
    <p className="story-help">The character’s path through the story, in story order. Link an event to the scene or beat where it happens.</p>
    {ordered.length === 0 && <p className="empty-copy">No events yet.</p>}
    <ol className="timeline-events">
      {ordered.map((row, index) => <EventRow key={`${row.id}-${row.version}`} row={row} index={index} count={ordered.length} scenes={scenes} beats={beats}
        onMove={delta => move(index, delta)} onDelete={() => setDeleting(row)}
        onSave={fields => run(() => storyApi.updateEvent(projectId, row, fields), 'Unable to save the event')} />)}
    </ol>
    <form className="story-card" aria-label="New timeline event" onSubmit={event => void add(event)}>
      <EventFields form={form} onChange={setForm} scenes={scenes} beats={beats} idPrefix="new-event" />
      <button className="button quiet" type="submit" disabled={!form.title.trim()}>Add event</button>
    </form>
    {error && <p className="copilot-error" role="alert">{error}</p>}
    {deleting && <ConfirmDialog title={`Delete “${deleting.title}”?`} confirmLabel="Delete event" onCancel={() => setDeleting(null)}
      onConfirm={() => { const row = deleting; setDeleting(null); void run(() => storyApi.deleteEvent(projectId, row), 'Unable to delete the event') }} />}
  </section>
}
