import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api'
import { errorMessage, keys, useCharacters } from '../data/queries'
import { type Character, type CharacterFields, storyApi } from '../storyApi'
import CharacterTimeline from './CharacterTimeline'
import ConfirmDialog from './ConfirmDialog'
import { splitList, TextField, useFocusField, useSaveShortcut } from './fields'
import RelationshipsEditor from './RelationshipsEditor'
import { SourceBadge } from './CharactersPage'
import { useEdits } from './useEdits'
import { useProjectId } from './useProjectId'

type ProfileField = 'name' | 'role' | 'summary' | 'bio' | 'want' | 'need' | 'motive' | 'objective' | 'flaw' | 'arc_summary' | 'voice' | 'notes' | 'aliases' | 'tags'
const PROFILE: { name: ProfileField; label: string; rows?: number; hint?: string }[] = [
  { name: 'name', label: 'Name' },
  { name: 'role', label: 'Role' },
  { name: 'summary', label: 'Summary', rows: 2, hint: 'One or two lines the room sees first.' },
  { name: 'want', label: 'Want', rows: 2, hint: 'The conscious, external goal.' },
  { name: 'need', label: 'Need', rows: 2, hint: 'What they actually need, often unaware.' },
  { name: 'motive', label: 'Motive', rows: 2, hint: 'Why they act.' },
  { name: 'objective', label: 'Objective', rows: 2, hint: 'What they pursue across the story.' },
  { name: 'flaw', label: 'Flaw', rows: 2 },
  { name: 'arc_summary', label: 'Arc', rows: 3, hint: 'Who they are at the start and who they become.' },
  { name: 'bio', label: 'Biography', rows: 4 },
  { name: 'voice', label: 'Voice', rows: 2, hint: 'How they talk.' },
  { name: 'notes', label: 'Notes', rows: 3 },
  { name: 'aliases', label: 'Aliases', hint: 'Comma-separated; also used to match dialogue cues.' },
  { name: 'tags', label: 'Tags', hint: 'Comma-separated.' },
]

function ProfileForm({ projectId, row }: { projectId: number; row: Character }) {
  const queryClient = useQueryClient()
  const edits = useEdits<ProfileField>(row)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  useFocusField('character', true)

  async function save(): Promise<void> {
    if (!edits.dirty || saving) return
    const changes: CharacterFields = {}
    for (const [name, text] of Object.entries(edits.changed) as [ProfileField, string][]) {
      if (name === 'aliases' || name === 'tags') changes[name] = splitList(text)
      else changes[name] = name === 'name' ? text.trim() : text
    }
    setSaving(true); setError(''); setStatus('')
    try {
      const saved = await storyApi.updateCharacter(projectId, row, changes)
      queryClient.setQueryData<Character[]>(keys.characters(projectId), current => current?.map(item => item.id === saved.id ? saved : item))
      edits.reset()
      setStatus('Profile saved.')
      void queryClient.invalidateQueries({ queryKey: keys.twin(projectId) })
    } catch (reason) {
      setError(errorMessage(reason, 'Unable to save the profile'))
      if (reason instanceof ApiError && reason.status === 409) void queryClient.invalidateQueries({ queryKey: keys.characters(projectId) })
    } finally { setSaving(false) }
  }
  useSaveShortcut(() => void save(), edits.dirty)

  return <form className="story-form profile-form" aria-label={`${row.name} profile`} onSubmit={event => { event.preventDefault(); void save() }}>
    {PROFILE.map(field => <TextField key={field.name} id={`character-${field.name}`} label={field.label} rows={field.rows} hint={field.hint}
      list={field.name === 'role' ? 'character-roles' : undefined} value={edits.value(field.name)} onChange={value => { edits.set(field.name, value); setStatus('') }} />)}
    {error && <p className="notice" role="alert">{error}</p>}
    <div className="story-actions sticky">
      <button className="button primary" type="submit" disabled={!edits.dirty || saving}>{saving ? 'Saving…' : edits.dirty ? 'Save profile' : 'Saved'}</button>
      {edits.dirty && <button className="button quiet" type="button" onClick={edits.reset}>Discard changes</button>}
      {status && <span className="settings-success" role="status">{status}</span>}
    </div>
  </form>
}

/** One character: profile form, relationships, timeline, and delete. */
export default function CharacterDetail() {
  const projectId = useProjectId()
  const characterId = Number(useParams().characterId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: cast, isPending } = useCharacters(projectId)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')
  const row = cast?.find(item => item.id === characterId)

  async function remove(target: Character): Promise<void> {
    try {
      await storyApi.deleteCharacter(projectId, target)
      setConfirming(false)
      queryClient.setQueryData<Character[]>(keys.characters(projectId), current => current?.filter(item => item.id !== target.id))
      for (const key of [keys.characters(projectId), keys.relationships(projectId), keys.timelines(projectId), keys.beats(projectId)]) void queryClient.invalidateQueries({ queryKey: key })
      navigate(`/projects/${projectId}/characters`)
    } catch (reason) { setConfirming(false); setError(errorMessage(reason, 'Unable to delete the character')) }
  }

  if (isPending) return <section className="story-detail"><p className="empty-copy">Loading…</p></section>
  if (!row) return <section className="story-detail"><p className="empty-copy">This character no longer exists.</p></section>
  return <section className="story-detail" aria-label={`Character ${row.name}`}>
    <div className="story-detail-head">
      <h2>{row.name}</h2>
      <SourceBadge source={row.source} edited={row.writer_edited} />
      {row.scene_ids.length > 0 && <small>{row.dialogue_lines} lines · {row.scene_ids.length} scenes</small>}
      <button className="button quiet danger" type="button" onClick={() => setConfirming(true)}>Delete character</button>
    </div>
    {error && <p className="notice" role="alert">{error}</p>}
    <ProfileForm key={row.id} projectId={projectId} row={row} />
    <RelationshipsEditor projectId={projectId} character={row} cast={cast ?? []} />
    <CharacterTimeline key={`timeline-${row.id}`} projectId={projectId} character={row} />
    {confirming && <ConfirmDialog title={`Delete ${row.name}?`} confirmLabel="Delete character" onCancel={() => setConfirming(false)} onConfirm={() => void remove(row)}>
      <p>Their profile, relationships and timeline events are removed. Scenes and beats stay; they just lose the link.</p>
    </ConfirmDialog>}
  </section>
}
