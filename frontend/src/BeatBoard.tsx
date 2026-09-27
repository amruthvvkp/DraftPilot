import { useEffect, useState } from 'react'
import { createArtifact, listArtifacts, StoryArtifact, updateArtifact } from './api'
import './room.css'

type Beat = { title: string; summary: string; act: number; sequence?: number }
const ACTS = [1, 2, 3]

/** Read the outline's beats, normalising the act of beats that don't carry one. */
function beatsOf(outline: StoryArtifact | undefined): Beat[] {
  const raw = outline?.artifact_metadata?.beats
  return Array.isArray(raw) ? raw.map(item => ({ title: String(item.title ?? ''), summary: String(item.summary ?? ''), act: ACTS.includes(Number(item.act)) ? Number(item.act) : 1 })) : []
}

/** Render beats as the markdown the Outline artifact holds. */
function outlineMarkdown(beats: Beat[]): string {
  return ACTS.map(act => [`## Act ${act}`, ...beats.filter(beat => beat.act === act).map(beat => `- **${beat.title}** — ${beat.summary}`)].join('\n')).join('\n\n')
}

/** Arrange the outline's beats across three acts: move, reorder, edit, add, and save as a new version. */
export default function BeatBoard({ projectId }: { projectId: number }) {
  const [outline, setOutline] = useState<StoryArtifact | undefined>()
  const [beats, setBeats] = useState<Beat[]>([])
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  async function load(): Promise<void> {
    try {
      const found = (await listArtifacts(projectId)).find(item => item.kind === 'outline')
      setOutline(found)
      setBeats(beatsOf(found))
      setDirty(false)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load the outline') }
  }

  useEffect(() => { void load() }, [projectId])

  function change(next: Beat[]): void { setBeats(next); setDirty(true); setSaved(false) }
  function move(index: number, delta: number): void {
    const act = beats[index].act
    const same = beats.map((beat, position) => ({ beat, position })).filter(item => item.beat.act === act)
    const at = same.findIndex(item => item.position === index)
    const swap = same[at + delta]
    if (!swap) return
    const next = [...beats]
    ;[next[index], next[swap.position]] = [next[swap.position], next[index]]
    change(next)
  }
  function shift(index: number, delta: number): void {
    const act = Math.min(3, Math.max(1, beats[index].act + delta))
    change(beats.map((beat, position) => position === index ? { ...beat, act } : beat))
  }

  async function save(): Promise<void> {
    setError('')
    try {
      const target = outline ?? await createArtifact(projectId, 'outline', 'Outline')
      const ordered = ACTS.flatMap(act => beats.filter(beat => beat.act === act)).map((beat, index) => ({ ...beat, sequence: index + 1 }))
      setOutline(await updateArtifact(projectId, target.id, target.version, { content: outlineMarkdown(ordered), metadata: { ...target.artifact_metadata, beats: ordered } }))
      setBeats(ordered)
      setDirty(false)
      setSaved(true)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save the outline') }
  }

  return <div className="room-page beat-page">
    <header className="room-head"><a className="room-back" href={`/projects/${projectId}`}>← Workspace</a><p className="eyebrow warm">BEAT BOARD</p><h1>Shape the story</h1>
      <p>Your Outline's beats, act by act. Move them, reorder them and rewrite them, then save a new version. <strong>Outline → scenes</strong> in the writers' room drafts from exactly these beats.</p>
      <div className="twin-actions"><button className="button primary" onClick={() => void save()} disabled={!dirty}>{dirty ? 'Save outline' : 'Saved'}</button><button className="button quiet" onClick={() => change([...beats, { title: 'New beat', summary: '', act: 1 }])}>＋ Add beat</button>{dirty && <button className="button quiet" onClick={() => void load()}>Discard changes</button>}<a className="button quiet" href={`/projects/${projectId}/room`}>Writers’ room ↗</a></div>
      {saved && <p className="settings-success" role="status">Saved as version {outline?.version}.</p>}
    </header>
    {error && <p className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    {beats.length === 0 && <p className="empty-copy">No beats yet. Add one, or run <strong>Notes → outline</strong> in the writers’ room and approve its outline.</p>}
    <div className="beat-board">{ACTS.map(act => <section key={act} className="beat-column" aria-label={`Act ${act}`}>
      <p className="eyebrow">ACT {act} / {beats.filter(beat => beat.act === act).length}</p>
      {beats.map((beat, index) => beat.act !== act ? null : <article className="beat-card" key={index}>
        <input aria-label="Beat title" value={beat.title} onChange={event => change(beats.map((item, position) => position === index ? { ...item, title: event.target.value } : item))} />
        <textarea aria-label={`What happens in ${beat.title}`} value={beat.summary} rows={3} onChange={event => change(beats.map((item, position) => position === index ? { ...item, summary: event.target.value } : item))} />
        <div className="beat-tools" role="group" aria-label={`Move ${beat.title}`}>
          <button aria-label="Earlier" onClick={() => move(index, -1)}>↑</button><button aria-label="Later" onClick={() => move(index, 1)}>↓</button>
          <button aria-label="Previous act" disabled={act === 1} onClick={() => shift(index, -1)}>←</button><button aria-label="Next act" disabled={act === 3} onClick={() => shift(index, 1)}>→</button>
          <button aria-label="Remove beat" className="danger" onClick={() => change(beats.filter((_item, position) => position !== index))}>×</button>
        </div>
      </article>)}
    </section>)}</div>
  </div>
}
