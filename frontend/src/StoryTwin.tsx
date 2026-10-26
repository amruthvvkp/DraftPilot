import { useEffect, useState } from 'react'
import { getStoryTwin, refreshStoryTwin, StoryTwin, subscribeProjectEvents } from './api'
import { Character, Location, storyApi } from './storyApi'
import './room.css'

const owned = (row: Character | Location) => row.source !== 'twin' || row.writer_edited

/** The Story twin: what the room knows about your cast and world, derived from the draft and editable by you. */
export default function StoryTwinPage({ projectId }: { projectId: number }) {
  const [twin, setTwin] = useState<StoryTwin | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')

  async function load(): Promise<void> {
    try { setTwin(await getStoryTwin(projectId)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load the Story twin') }
  }

  useEffect(() => {
    void load()
    return subscribeProjectEvents(projectId, event => { if (event.kind === 'scene.changed') window.setTimeout(() => void load(), 6000) })
  }, [projectId])

  async function refresh(): Promise<void> {
    setBusy(true)
    try { await refreshStoryTwin(projectId); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to refresh') } finally { setBusy(false) }
  }

  async function save(change: () => Promise<unknown>): Promise<void> {
    try { await change(); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save the note') }
  }

  const match = (row: Character | Location) => row.name.toLowerCase().includes(query.toLowerCase())
  const topLines = Math.max(1, ...(twin?.characters ?? []).map(row => row.dialogue_lines))
  return <div className="room-page twin-page">
    <header className="room-head"><a className="room-back" href={`/projects/${projectId}`}>← Workspace</a><p className="eyebrow warm">STORY TWIN</p><h1>What the room knows</h1>
      <p>Derived from your working draft and refreshed a few seconds after you edit. Every agent reads this before it works. Write your own note on any character or place: the room keeps it and never overwrites it.</p>
      <div className="twin-actions"><input aria-label="Filter the Story twin" placeholder="Filter by name…" value={query} onChange={event => setQuery(event.target.value)} /><button className="button quiet" onClick={() => void refresh()} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh from the draft'}</button><a className="button quiet" href={`/projects/${projectId}/room`}>Writers’ room ↗</a></div>
    </header>
    {error && <p className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    {twin && <div className="twin-grid">
      <section aria-label="Characters"><p className="eyebrow">CHARACTERS / {twin.characters.length}</p>
        {twin.characters.filter(match).map(row => <article className="twin-card" key={row.id}>
          <div className="twin-card-head"><strong><a href={`/projects/${projectId}/characters/${row.id}`}>{row.name}</a></strong>{owned(row) && <span className="badge proposes" title="You wrote or edited this">yours</span>}<small>{row.dialogue_lines} lines · {row.scene_ids.length} scenes</small></div>
          <div className="twin-bar" aria-hidden="true"><span style={{ width: `${(row.dialogue_lines / topLines) * 100}%` }} /></div>
          <textarea aria-label={`Note on ${row.name}`} defaultValue={row.summary} onBlur={event => { if (event.target.value !== row.summary) void save(() => storyApi.updateCharacter(projectId, row, { summary: event.target.value })) }} rows={2} />
        </article>)}
      </section>
      <section aria-label="Locations"><p className="eyebrow">LOCATIONS / {twin.locations.length}</p>
        {twin.locations.filter(match).map(row => <article className="twin-card" key={row.id}>
          <div className="twin-card-head"><strong>{row.name}</strong>{owned(row) && <span className="badge proposes">yours</span>}<small>{row.int_ext.join('/') || '—'} · {row.times.join(', ') || 'any time'} · {row.scene_ids.length} scenes</small></div>
          <textarea aria-label={`Note on ${row.name}`} defaultValue={row.description} onBlur={event => { if (event.target.value !== row.description) void save(() => storyApi.updateLocation(projectId, row, { description: event.target.value })) }} rows={1} />
        </article>)}
      </section>
    </div>}
    {twin && twin.characters.length === 0 && <p className="empty-copy">No characters yet. Write or import some scenes, and the twin fills in by itself.</p>}
  </div>
}
