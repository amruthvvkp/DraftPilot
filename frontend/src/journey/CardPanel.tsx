import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import type { Beat, Character, StoryMoment, StoryMomentFields, TimelineEvent, TimelineEventFields } from '../storyApi'
import type { Move } from './JourneyCanvas'
import type { SceneLite } from './layout'

type Common = { projectId: number; scenes: SceneLite[]; beats: Beat[]; narrative: boolean; onMove: (move: Move) => void; onClose: () => void }

/** Parse a story-world position field: blank is undated. */
function parseChrono(value: string): number | null {
  const trimmed = value.trim()
  return trimmed === '' || Number.isNaN(Number(trimmed)) ? null : Number(trimmed)
}

/** The move buttons: the keyboard equivalents of dragging a card. */
function MoveButtons({ narrative, onMove }: { narrative: boolean; onMove: (move: Move) => void }) {
  return <div className="journey-moves" role="group" aria-label="Move card">
    <button type="button" className="button quiet small" onClick={() => onMove('earlier')}>Earlier</button>
    <button type="button" className="button quiet small" onClick={() => onMove('later')}>Later</button>
    {narrative && <>
      <button type="button" className="button quiet small" onClick={() => onMove('previous-act')}>Previous act</button>
      <button type="button" className="button quiet small" onClick={() => onMove('next-act')}>Next act</button>
    </>}
    <small>Or focus the card and press Alt + arrow keys.</small>
  </div>
}

/** Scene and beat pickers, with links to open them. */
function Links({ projectId, scenes, beats, sceneId, beatId, setSceneId, setBeatId }: { projectId: number; scenes: SceneLite[]; beats: Beat[]; sceneId: string; beatId: string; setSceneId: (value: string) => void; setBeatId: (value: string) => void }) {
  return <>
    <label>Scene<select value={sceneId} onChange={event => setSceneId(event.target.value)}>
      <option value="">No scene</option>
      {scenes.map(scene => <option key={scene.id} value={scene.id}>{scene.heading}</option>)}
    </select></label>
    <label>Beat<select value={beatId} onChange={event => setBeatId(event.target.value)}>
      <option value="">No beat</option>
      {beats.map(beat => <option key={beat.id} value={beat.id}>{beat.title}</option>)}
    </select></label>
    <p className="journey-links">
      {sceneId && <Link to={`/projects/${projectId}/script`}>Open in script</Link>}
      {beatId && <Link to={`/projects/${projectId}/outline`}>Open in outline</Link>}
    </p>
  </>
}

/** Edit one character's card (a direct, versioned edit — not a proposal). */
export function EventPanel({ projectId, event, character, moment, scenes, beats, narrative, onSave, onLeaveMoment, onMove, onClose }: Common & {
  event: TimelineEvent; character?: Character; moment?: StoryMoment
  onSave: (fields: TimelineEventFields) => void; onLeaveMoment: () => void
}) {
  const [title, setTitle] = useState(event.title)
  const [storyTime, setStoryTime] = useState(event.story_time)
  const [chrono, setChrono] = useState(event.chrono_index === null ? '' : String(event.chrono_index))
  const [objective, setObjective] = useState(event.objective)
  const [motivation, setMotivation] = useState(event.motivation)
  const [emotion, setEmotion] = useState(event.emotional_state)
  const [history, setHistory] = useState(event.history)
  const [description, setDescription] = useState(event.description)
  const [intensity, setIntensity] = useState(event.intensity)
  const [sceneId, setSceneId] = useState(event.scene_id === null ? '' : String(event.scene_id))
  const [beatId, setBeatId] = useState(event.beat_id === null ? '' : String(event.beat_id))
  function submit(formEvent: FormEvent): void {
    formEvent.preventDefault()
    onSave({
      title: title.trim() || event.title, story_time: storyTime, chrono_index: parseChrono(chrono), objective, motivation, emotional_state: emotion,
      history, description, intensity, scene_id: sceneId ? Number(sceneId) : null, beat_id: beatId ? Number(beatId) : null,
    })
  }
  return <aside className="journey-panel" aria-label={`Edit ${event.title}`}>
    <header><p className="eyebrow warm">{character?.name ?? 'Card'}{moment ? ` · in “${moment.title}”` : ''}</p><button type="button" className="button quiet small" onClick={onClose}>Close</button></header>
    <MoveButtons narrative={narrative} onMove={onMove} />
    <form onSubmit={submit}>
      <label>Title<input value={title} onChange={change => setTitle(change.target.value)} /></label>
      <div className="journey-pair">
        <label>Story time<input value={storyTime} placeholder="1973, Day 3…" onChange={change => setStoryTime(change.target.value)} /></label>
        <label>Story order<input inputMode="decimal" value={chrono} placeholder="undated" onChange={change => setChrono(change.target.value)} /></label>
      </div>
      <label>Objective<textarea rows={2} value={objective} onChange={change => setObjective(change.target.value)} /></label>
      <label>Motivation<textarea rows={2} value={motivation} onChange={change => setMotivation(change.target.value)} /></label>
      <label>Emotional state<input value={emotion} onChange={change => setEmotion(change.target.value)} /></label>
      <label>Intensity <output>{intensity > 0 ? `+${intensity}` : intensity}</output>
        <input type="range" aria-label="Intensity" aria-valuetext={`${intensity} (−5 a low, +5 a high)`} min={-5} max={5} step={1} value={intensity} onChange={change => setIntensity(Number(change.target.value))} />
      </label>
      <label>History<textarea rows={2} value={history} onChange={change => setHistory(change.target.value)} /></label>
      <label>Description<textarea rows={3} value={description} onChange={change => setDescription(change.target.value)} /></label>
      {!moment && <Links projectId={projectId} scenes={scenes} beats={beats} sceneId={sceneId} beatId={beatId} setSceneId={setSceneId} setBeatId={setBeatId} />}
      <div className="journey-panel-actions">
        {moment && <button type="button" className="button quiet small" onClick={onLeaveMoment}>Leave shared moment</button>}
        <button type="submit" className="button primary small">Save card</button>
      </div>
    </form>
  </aside>
}

/** Edit a shared moment: what happened, when, and where it sits; each side opens its own card. */
export function MomentPanel({ projectId, moment, participants, characters, scenes, beats, narrative, onSave, onDelete, onOpen, onMove, onClose }: Common & {
  moment: StoryMoment; participants: TimelineEvent[]; characters: Map<number, Character>
  onSave: (fields: StoryMomentFields) => void; onDelete: () => void; onOpen: (eventId: number) => void
}) {
  const [title, setTitle] = useState(moment.title)
  const [summary, setSummary] = useState(moment.summary)
  const [storyTime, setStoryTime] = useState(moment.story_time)
  const [chrono, setChrono] = useState(moment.chrono_index === null ? '' : String(moment.chrono_index))
  const [sceneId, setSceneId] = useState(moment.scene_id === null ? '' : String(moment.scene_id))
  const [beatId, setBeatId] = useState(moment.beat_id === null ? '' : String(moment.beat_id))
  function submit(formEvent: FormEvent): void {
    formEvent.preventDefault()
    onSave({ title: title.trim() || moment.title, summary, story_time: storyTime, chrono_index: parseChrono(chrono), scene_id: sceneId ? Number(sceneId) : null, beat_id: beatId ? Number(beatId) : null })
  }
  return <aside className="journey-panel" aria-label={`Edit ${moment.title}`}>
    <header><p className="eyebrow warm">Shared moment</p><button type="button" className="button quiet small" onClick={onClose}>Close</button></header>
    <MoveButtons narrative={narrative} onMove={onMove} />
    <form onSubmit={submit}>
      <label>Title<input value={title} onChange={change => setTitle(change.target.value)} /></label>
      <label>What happens<textarea rows={3} value={summary} onChange={change => setSummary(change.target.value)} /></label>
      <div className="journey-pair">
        <label>Story time<input value={storyTime} onChange={change => setStoryTime(change.target.value)} /></label>
        <label>Story order<input inputMode="decimal" value={chrono} placeholder="undated" onChange={change => setChrono(change.target.value)} /></label>
      </div>
      <Links projectId={projectId} scenes={scenes} beats={beats} sceneId={sceneId} beatId={beatId} setSceneId={setSceneId} setBeatId={setBeatId} />
      <div className="journey-panel-actions">
        <button type="button" className="button quiet small" onClick={onDelete}>Dissolve moment</button>
        <button type="submit" className="button primary small">Save moment</button>
      </div>
    </form>
    <section aria-label="Who is in it">
      <p className="eyebrow warm">Who is in it</p>
      <ul className="journey-sides">{participants.map(event => <li key={event.id}>
        <button type="button" className="button quiet small" onClick={() => onOpen(event.id)}>{characters.get(event.character_id)?.name ?? 'Character'}: {event.title}</button>
      </li>)}</ul>
    </section>
  </aside>
}
