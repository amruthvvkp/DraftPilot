import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { errorMessage, keys, useRelationships } from '../data/queries'
import { type Character, type Relationship, storyApi } from '../storyApi'

type Props = { projectId: number; character: Character; cast: Character[] }

function RelationshipRow({ projectId, relationship, character, other, onError }: { projectId: number; relationship: Relationship; character: Character; other?: Character; onError: (message: string) => void }) {
  const queryClient = useQueryClient()
  const [relation, setRelation] = useState(relationship.relation)
  const outgoing = relationship.source_character_id === character.id
  const otherName = other?.name ?? 'Unknown'

  async function run(change: () => Promise<unknown>, fallback: string): Promise<void> {
    try { await change() } catch (reason) { onError(errorMessage(reason, fallback)) }
    void queryClient.invalidateQueries({ queryKey: keys.relationships(projectId) })
  }

  function saveRelation(): void {
    if (!relation.trim() || relation === relationship.relation) return
    void run(() => storyApi.updateRelationship(projectId, relationship, { relation: relation.trim() }), 'Unable to save the relationship')
  }

  return <li className="relationship-row">
    <span>{outgoing ? character.name : <Link to={`/projects/${projectId}/characters/${relationship.source_character_id}`}>{otherName}</Link>}</span>
    <input aria-label={`Relation between ${character.name} and ${otherName}`} value={relation} onChange={event => setRelation(event.target.value)}
      onBlur={saveRelation} onKeyDown={event => { if (event.key === 'Enter') saveRelation() }} />
    <span>{outgoing ? <Link to={`/projects/${projectId}/characters/${relationship.target_character_id}`}>{otherName}</Link> : character.name}</span>
    <button type="button" className="mini-button danger" aria-label={`Remove relationship with ${otherName}`}
      onClick={() => void run(() => storyApi.deleteRelationship(projectId, relationship), 'Unable to remove the relationship')}>✕</button>
  </li>
}

/** List and edit a character's relationships to the rest of the cast. */
export default function RelationshipsEditor({ projectId, character, cast }: Props) {
  const queryClient = useQueryClient()
  const { data: relationships } = useRelationships(projectId)
  const [targetId, setTargetId] = useState('')
  const [relation, setRelation] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const others = cast.filter(row => row.id !== character.id)
  const mine = (relationships ?? []).filter(row => row.source_character_id === character.id || row.target_character_id === character.id)
  const nameOf = (id: number) => cast.find(row => row.id === id)

  async function add(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!targetId || !relation.trim()) return
    setError('')
    try {
      await storyApi.createRelationship(projectId, { source_character_id: character.id, target_character_id: Number(targetId), relation: relation.trim(), description: description.trim() })
      setRelation(''); setDescription(''); setTargetId('')
    } catch (reason) { setError(errorMessage(reason, 'Unable to add the relationship')) }
    void queryClient.invalidateQueries({ queryKey: keys.relationships(projectId) })
  }

  return <section className="story-subsection" aria-label="Relationships">
    <h3>Relationships</h3>
    {mine.length === 0 && <p className="empty-copy">No relationships yet.</p>}
    <ul className="relationship-list">
      {mine.map(row => <RelationshipRow key={`${row.id}-${row.version}`} projectId={projectId} relationship={row} character={character}
        other={nameOf(row.source_character_id === character.id ? row.target_character_id : row.source_character_id)} onError={setError} />)}
    </ul>
    {others.length > 0 ? <form className="story-inline-form" aria-label="New relationship" onSubmit={event => void add(event)}>
      <select aria-label="Related character" value={targetId} onChange={event => setTargetId(event.target.value)}>
        <option value="">Choose a character…</option>
        {others.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      <input aria-label="Relation" placeholder="e.g. father of, rival" value={relation} onChange={event => setRelation(event.target.value)} />
      <input aria-label="Relationship description" placeholder="Optional detail" value={description} onChange={event => setDescription(event.target.value)} />
      <button className="button quiet" type="submit" disabled={!targetId || !relation.trim()}>Add relationship</button>
    </form> : <p className="empty-copy">Add another character to relate them.</p>}
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </section>
}
