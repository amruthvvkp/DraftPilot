import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api'
import { errorMessage, keys, useStoryline } from '../data/queries'
import { type Storyline, storyApi, type StorylineFields } from '../storyApi'
import { TextField, useFocusField, useSaveShortcut } from './fields'
import { useEdits } from './useEdits'
import { useProjectId } from './useProjectId'

type FieldName = keyof StorylineFields
const FIELDS: { name: FieldName; label: string; rows: number; hint: string }[] = [
  { name: 'title', label: 'Title', rows: 1, hint: 'The working title.' },
  { name: 'logline', label: 'Logline', rows: 2, hint: 'One sentence: who wants what, and what stands in the way.' },
  { name: 'premise', label: 'Premise', rows: 3, hint: 'The dramatic question the story asks.' },
  { name: 'synopsis', label: 'Synopsis', rows: 8, hint: 'Beginning, middle and end in prose.' },
  { name: 'theme', label: 'Theme', rows: 2, hint: 'What the story is really about.' },
  { name: 'tone', label: 'Tone', rows: 2, hint: 'Mood, register and genre feel.' },
  { name: 'description', label: 'Description', rows: 3, hint: 'Pitch notes or a longer description.' },
  { name: 'story_outline', label: 'Story notes', rows: 6, hint: 'Free-form outline notes (structured beats live on the Outline page).' },
]

/** Edit the project's storyline: title, logline, premise, synopsis, theme, tone and notes. */
export default function StorylinePage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const { data: storyline, error: loadError } = useStoryline(projectId)
  const edits = useEdits<FieldName>(storyline)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  useFocusField('storyline', Boolean(storyline))

  const save = useCallback(async (): Promise<void> => {
    if (!storyline || !edits.dirty || saving) return
    const changes: Record<string, string | null> = {}
    for (const [name, text] of Object.entries(edits.changed) as [FieldName, string][]) {
      changes[name] = name === 'title' ? text.trim() : text.trim() ? text : null
    }
    setSaving(true); setError(''); setStatus('')
    try {
      const saved = await storyApi.updateStoryline(projectId, storyline.version, changes as StorylineFields)
      queryClient.setQueryData<Storyline>(keys.storyline(projectId), current => current && { ...current, ...changes, version: saved.version })
      edits.reset()
      setConflict(false)
      setStatus('Storyline saved.')
      void queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
      void queryClient.invalidateQueries({ queryKey: keys.projects })
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setConflict(true)
        await queryClient.invalidateQueries({ queryKey: keys.storyline(projectId) })
      } else setError(errorMessage(reason, 'Unable to save the storyline'))
    } finally { setSaving(false) }
  }, [edits, projectId, queryClient, saving, storyline])
  useSaveShortcut(() => void save(), edits.dirty)

  function discard(): void { edits.reset(); setConflict(false); setStatus('') }

  if (loadError) return <main className="story-page"><p className="notice" role="alert">{errorMessage(loadError, 'Unable to load the storyline')}</p></main>
  return <main className="story-page">
    <header className="story-head">
      <p className="eyebrow warm">STEP 1 · STORYLINE</p>
      <h1>Storyline</h1>
      <p>The spine every later step builds on. Agents read these fields as the project brief.</p>
    </header>
    {conflict && <div className="notice" role="alert">
      This storyline changed in another session, by an agent or an MCP client. Your edits are kept; the other fields now show the latest version.
      <div className="story-actions"><button className="button primary" onClick={() => void save()}>Save my version</button><button className="button quiet" onClick={discard}>Discard my edits</button></div>
    </div>}
    {error && <p className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    {!storyline && <p className="empty-copy">Loading…</p>}
    {storyline && <form className="story-form" aria-label="Storyline" onSubmit={event => { event.preventDefault(); void save() }}>
      {FIELDS.map(field => <TextField key={field.name} id={`storyline-${field.name}`} label={field.label} rows={field.rows} hint={field.hint}
        value={edits.value(field.name)} onChange={value => { edits.set(field.name, value); setStatus('') }} />)}
      <div className="story-actions sticky">
        <button className="button primary" type="submit" disabled={!edits.dirty || saving}>{saving ? 'Saving…' : edits.dirty ? 'Save storyline' : 'Saved'}</button>
        {edits.dirty && <button className="button quiet" type="button" onClick={discard}>Discard changes</button>}
        {status && <span className="settings-success" role="status">{status}</span>}
        <small>Version {storyline.version} · Ctrl/⌘+S saves</small>
      </div>
    </form>}
  </main>
}
