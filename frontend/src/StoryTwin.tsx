import { useState } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { refreshStoryTwin } from './api'
import { errorMessage, keys, useTwin } from './data/queries'
import { Character, Location, storyApi } from './storyApi'
import './room.css'

const owned = (row: Character | Location) => row.source !== 'twin' || row.writer_edited

/** The Story twin: what the room knows about your cast and world, derived from the draft and editable by you. */
export default function StoryTwinPage({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const { data: twin, error: loadError } = useTwin(projectId)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const reload = () => queryClient.invalidateQueries({ queryKey: keys.project(projectId) })

  async function refresh(): Promise<void> {
    setBusy(true)
    try { await refreshStoryTwin(projectId); await reload() } catch (reason) { setError(errorMessage(reason, 'Unable to refresh')) } finally { setBusy(false) }
  }

  async function save(change: () => Promise<unknown>): Promise<void> {
    try { await change() } catch (reason) { setError(errorMessage(reason, 'Unable to save the note')) }
    await reload()
  }

  const match = (row: Character | Location) => row.name.toLowerCase().includes(query.toLowerCase())
  const topLines = Math.max(1, ...(twin?.characters ?? []).map(row => row.dialogue_lines))
  const shownError = error || (loadError ? errorMessage(loadError, 'Unable to load the Story twin') : '')
  return <div className="room-page twin-page">
    <header className="room-head">
      <Link className="room-back" to={`/projects/${projectId}`}>← Workspace</Link>
      <p className="eyebrow warm">STORY TWIN</p>
      <h1>What the room knows</h1>
      <p>Derived from your working draft and refreshed a few seconds after you edit. Every agent reads this before it works. Write your own note on any character or place: the room keeps it and never overwrites it.</p>
      <div className="twin-actions">
        <input aria-label="Filter the Story twin" placeholder="Filter by name…" value={query} onChange={event => setQuery(event.target.value)} />
        <button className="button quiet" onClick={() => void refresh()} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh from the draft'}</button>
        <Link className="button quiet" to={`/projects/${projectId}/context-map`}>Context map ↗</Link>
        <Link className="button quiet" to={`/projects/${projectId}/room`}>Writers’ room ↗</Link>
      </div>
    </header>
    {shownError && <p className="notice" role="alert">{shownError}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    {twin && <div className="twin-grid">
      <section aria-label="Characters"><p className="eyebrow">CHARACTERS / {twin.characters.length}</p>
        {twin.characters.filter(match).map(row => <article className="twin-card" key={row.id}>
          <div className="twin-card-head">
            <strong><Link to={`/projects/${projectId}/characters/${row.id}`}>{row.name}</Link></strong>
            {owned(row) && <span className="badge proposes" title="You wrote or edited this">yours</span>}
            <small>{row.dialogue_lines} lines · {row.scene_ids.length} scenes</small>
          </div>
          <div className="twin-bar" aria-hidden="true"><span style={{ width: `${(row.dialogue_lines / topLines) * 100}%` }} /></div>
          <textarea key={row.version} aria-label={`Note on ${row.name}`} defaultValue={row.summary} rows={2}
            onBlur={event => { if (event.target.value !== row.summary) void save(() => storyApi.updateCharacter(projectId, row, { summary: event.target.value })) }} />
        </article>)}
      </section>
      <section aria-label="Locations"><p className="eyebrow">LOCATIONS / {twin.locations.length}</p>
        {twin.locations.filter(match).map(row => <article className="twin-card" key={row.id}>
          <div className="twin-card-head">
            <strong>{row.name}</strong>
            {owned(row) && <span className="badge proposes">yours</span>}
            <small>{row.int_ext.join('/') || '—'} · {row.times.join(', ') || 'any time'} · {row.scene_ids.length} scenes</small>
          </div>
          <textarea key={row.version} aria-label={`Note on ${row.name}`} defaultValue={row.description} rows={1}
            onBlur={event => { if (event.target.value !== row.description) void save(() => storyApi.updateLocation(projectId, row, { description: event.target.value })) }} />
        </article>)}
      </section>
    </div>}
    {twin && twin.characters.length === 0 && <p className="empty-copy">No characters yet. Write or import some scenes, and the twin fills in by itself.</p>}
  </div>
}
