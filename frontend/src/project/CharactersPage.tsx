import { type FormEvent, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { errorMessage, keys, useCharacters } from '../data/queries'
import { type Character, storyApi } from '../storyApi'
import { useProjectId } from './useProjectId'

export const ROLE_OPTIONS = ['protagonist', 'antagonist', 'deuteragonist', 'mentor', 'love interest', 'ally', 'supporting', 'minor']

const SOURCE_LABEL: Record<Character['source'], string> = { writer: 'yours', twin: 'from draft', agent: 'agent', import: 'imported' }

/** A source badge: who created the row. */
export function SourceBadge({ source, edited = false }: { source: Character['source']; edited?: boolean }) {
  return <span className={`badge source-${source}`} title="Where this came from">{source === 'twin' && edited ? 'from draft · edited' : SOURCE_LABEL[source]}</span>
}

function CastCard({ row, projectId }: { row: Character; projectId: number }) {
  const grounded = Boolean(row.motive.trim() && row.objective.trim())
  return <li>
    <NavLink to={`/projects/${projectId}/characters/${row.id}`} className={({ isActive }) => `cast-card${isActive ? ' active' : ''}`}>
      <strong>{row.name}</strong>
      <span className="cast-badges">{row.role && <span className="badge role">{row.role}</span>}<SourceBadge source={row.source} edited={row.writer_edited} /></span>
      <small>{grounded ? 'Motive & objective set' : 'Needs motive & objective'}{row.dialogue_lines ? ` · ${row.dialogue_lines} lines` : ''}</small>
    </NavLink>
  </li>
}

function CreateCharacter({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true); setError('')
    try {
      const cast = queryClient.getQueryData<Character[]>(keys.characters(projectId)) ?? []
      const created = await storyApi.createCharacter(projectId, { name: name.trim(), role: role.trim(), position: cast.length })
      queryClient.setQueryData<Character[]>(keys.characters(projectId), current => [...(current ?? []), created])
      void queryClient.invalidateQueries({ queryKey: keys.characters(projectId) })
      setName(''); setRole('')
      navigate(`/projects/${projectId}/characters/${created.id}`)
    } catch (reason) { setError(errorMessage(reason, 'Unable to create the character')) } finally { setBusy(false) }
  }

  return <form className="story-inline-form" aria-label="New character" onSubmit={event => void submit(event)}>
    <input aria-label="New character name" placeholder="Name" value={name} onChange={event => setName(event.target.value)} />
    <input aria-label="New character role" placeholder="Role" list="character-roles" value={role} onChange={event => setRole(event.target.value)} />
    <button className="button primary" type="submit" disabled={!name.trim() || busy}>Add character</button>
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </form>
}

/** The cast: every character with role and source, a create form, and the selected profile. */
export default function CharactersPage() {
  const projectId = useProjectId()
  const { data: cast, error } = useCharacters(projectId)
  return <main className="story-page">
    <header className="story-head">
      <p className="eyebrow warm">STEP 2 · CHARACTERS</p>
      <h1>Characters</h1>
      <p>Who wants what, and why. Profiles, relationships and each character’s own timeline.</p>
    </header>
    <datalist id="character-roles">{ROLE_OPTIONS.map(role => <option key={role} value={role} />)}</datalist>
    <div className="story-split">
      <section className="cast-list" aria-label="Cast">
        <CreateCharacter projectId={projectId} />
        {error && <p className="notice" role="alert">{errorMessage(error, 'Unable to load characters')}</p>}
        {cast && cast.length === 0 && <p className="empty-copy">No characters yet. Add your first above.</p>}
        <ul>{(cast ?? []).map(row => <CastCard key={row.id} row={row} projectId={projectId} />)}</ul>
      </section>
      <Outlet />
    </div>
  </main>
}

/** Shown when no character is selected. */
export function NoCharacterSelected() {
  return <section className="story-detail empty"><p className="empty-copy">Choose a character to edit their profile and timeline.</p></section>
}
