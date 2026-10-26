import { type FormEvent, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { errorMessage, keys, useLocations } from '../data/queries'
import { type Location, type LocationFields, storyApi } from '../storyApi'
import { SourceBadge } from './CharactersPage'
import ConfirmDialog from './ConfirmDialog'
import { TextField } from './fields'
import { useEdits } from './useEdits'
import { useProjectId } from './useProjectId'

type LocationField = 'name' | 'description' | 'visual_notes' | 'notes'

function LocationCard({ projectId, row, onDelete }: { projectId: number; row: Location; onDelete: () => void }) {
  const queryClient = useQueryClient()
  const edits = useEdits<LocationField>(row)
  const [error, setError] = useState('')

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!edits.dirty) return
    setError('')
    try {
      const saved = await storyApi.updateLocation(projectId, row, edits.changed as LocationFields)
      queryClient.setQueryData<Location[]>(keys.locations(projectId), current => current?.map(item => item.id === saved.id ? saved : item))
      edits.reset()
    } catch (reason) {
      setError(errorMessage(reason, 'Unable to save the location'))
      void queryClient.invalidateQueries({ queryKey: keys.locations(projectId) })
    }
  }

  const meta = [row.int_ext.join('/'), row.times.join(', '), row.scene_ids.length ? `${row.scene_ids.length} scenes` : ''].filter(Boolean).join(' · ')
  return <form className="story-card location-card" aria-label={`Location ${row.name}`} onSubmit={event => void save(event)}>
    <div className="story-detail-head"><h2>{row.name}</h2><SourceBadge source={row.source} edited={row.writer_edited} />{meta && <small>{meta}</small>}</div>
    <TextField id={`location-${row.id}-name`} label="Name" value={edits.value('name')} onChange={value => edits.set('name', value)} />
    <TextField id={`location-${row.id}-description`} label="Description" rows={2} value={edits.value('description')} onChange={value => edits.set('description', value)} />
    <TextField id={`location-${row.id}-visual`} label="Visual notes" rows={2} value={edits.value('visual_notes')} onChange={value => edits.set('visual_notes', value)} />
    <TextField id={`location-${row.id}-notes`} label="Notes" rows={2} value={edits.value('notes')} onChange={value => edits.set('notes', value)} />
    {error && <p className="copilot-error" role="alert">{error}</p>}
    <div className="story-actions">
      <button className="button primary" type="submit" disabled={!edits.dirty}>{edits.dirty ? 'Save location' : 'Saved'}</button>
      <button className="button quiet danger" type="button" onClick={onDelete}>Delete location</button>
    </div>
  </form>
}

/** The story's places: list, create, edit and delete. */
export default function LocationsPage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const { data: locations, error: loadError } = useLocations(projectId)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState<Location | null>(null)

  async function create(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!name.trim()) return
    setError('')
    try {
      await storyApi.createLocation(projectId, { name: name.trim(), position: locations?.length ?? 0 })
      setName('')
    } catch (reason) { setError(errorMessage(reason, 'Unable to add the location')) }
    void queryClient.invalidateQueries({ queryKey: keys.locations(projectId) })
  }

  async function remove(row: Location): Promise<void> {
    setDeleting(null)
    try { await storyApi.deleteLocation(projectId, row) } catch (reason) { setError(errorMessage(reason, 'Unable to delete the location')) }
    void queryClient.invalidateQueries({ queryKey: keys.locations(projectId) })
  }

  return <main className="story-page">
    <header className="story-head">
      <p className="eyebrow warm">WORLD · LOCATIONS</p>
      <h1>Locations</h1>
      <p>Every place in the story. Places you write in scene headings appear here by themselves; add your own notes to any of them.</p>
    </header>
    <form className="story-inline-form" aria-label="New location" onSubmit={event => void create(event)}>
      <input aria-label="New location name" placeholder="e.g. Bloom house" value={name} onChange={event => setName(event.target.value)} />
      <button className="button primary" type="submit" disabled={!name.trim()}>Add location</button>
    </form>
    {(error || loadError) && <p className="notice" role="alert">{error || errorMessage(loadError, 'Unable to load locations')}</p>}
    {locations && locations.length === 0 && <p className="empty-copy">No locations yet.</p>}
    <div className="location-grid">
      {(locations ?? []).map(row => <LocationCard key={row.id} projectId={projectId} row={row} onDelete={() => setDeleting(row)} />)}
    </div>
    {deleting && <ConfirmDialog title={`Delete ${deleting.name}?`} confirmLabel="Delete location" onCancel={() => setDeleting(null)} onConfirm={() => void remove(deleting)}>
      <p>Scenes keep their headings. If the draft still uses this place, the Story twin may derive it again.</p>
    </ConfirmDialog>}
  </main>
}
