import { useEffect, useState } from 'react'
import CopilotPanel from './CopilotPanel'
import { applyStoryOperation, createArtifact, listArtifacts, StoryArtifact, updateArtifact } from './api'

type ArtifactStudioProps = { projectId: number }

const artifactKinds = [
  ['brief', 'Brief / logline'],
  ['outline', 'Detailed outline'],
  ['character', 'Character story'],
  ['timeline', 'Timeline / beats'],
  ['canon', 'Story canon'],
  ['reference', 'Creative reference'],
] as const

export default function ArtifactStudio({ projectId }: ArtifactStudioProps) {
  const [artifacts, setArtifacts] = useState<StoryArtifact[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Record<number, { title: string; content: string }>>({})
  const [newKind, setNewKind] = useState('brief')
  const [newDependencies, setNewDependencies] = useState<number[]>([])
  const [operation, setOperation] = useState('add_beat')
  const [operationDraft, setOperationDraft] = useState<Record<string, string>>({ sequence: '1' })
  const [operationError, setOperationError] = useState('')
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try {
      const items = await listArtifacts(projectId)
      setArtifacts(items)
      setSelectedId(current => current ?? items[0]?.id ?? null)
      setDrafts(Object.fromEntries(items.map(item => [item.id, { title: item.title, content: item.content }])))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load story artifacts') }
  }

  useEffect(() => { void refresh() }, [projectId])

  async function addArtifact(): Promise<void> {
    const label = artifactKinds.find(item => item[0] === newKind)?.[1] ?? 'Story artifact'
    try {
      const item = await createArtifact(projectId, newKind, `New ${label.toLowerCase()}`, newDependencies)
      setArtifacts(current => [...current, item])
      setSelectedId(item.id)
      setDrafts(current => ({ ...current, [item.id]: { title: item.title, content: item.content } }))
      setNewDependencies([])
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create story artifact') }
  }

  async function save(item: StoryArtifact): Promise<void> {
    const draft = drafts[item.id]
    if (!draft || (draft.title === item.title && draft.content === item.content)) return
    try { await updateArtifact(projectId, item.id, item.version, draft); await refresh() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save story artifact') }
  }

  const selected = artifacts.find(item => item.id === selectedId)
  const draft = selected ? drafts[selected.id] : undefined

  function chooseOperation(value: string): void {
    setOperationDraft({ sequence: '1' })
    setOperationError('')
    setOperation(value)
  }

  const operationOptions = selected?.kind === 'brief'
    ? [['set_logline', 'Set logline']] as const
    : selected?.kind === 'character'
      ? [['add_character_arc', 'Add character arc']] as const
      : selected?.kind === 'canon'
        ? [['add_canon_rule', 'Add canon rule']] as const
        : selected?.kind === 'outline' || selected?.kind === 'timeline'
          ? [['add_beat', 'Add causal beat']] as const
          : []

  useEffect(() => {
    const nextOperation = selected?.kind === 'brief'
      ? 'set_logline'
      : selected?.kind === 'character'
        ? 'add_character_arc'
        : selected?.kind === 'canon'
          ? 'add_canon_rule'
          : 'add_beat'
    setOperation(nextOperation)
    setOperationDraft({ sequence: '1' })
  }, [selected?.kind])

  async function submitOperation(): Promise<void> {
    if (!selected) return
    const payload: Record<string, unknown> = { ...operationDraft }
    if (operation === 'add_beat') payload.sequence = Number(operationDraft.sequence || '1')
    if (operation !== 'add_beat') delete payload.sequence
    try {
      setOperationError('')
      await applyStoryOperation(projectId, selected.id, selected.version, operation, payload)
      await refresh()
    } catch (reason) {
      setOperationError(reason instanceof Error ? reason.message : 'Unable to apply story operation')
    }
  }

  return <div className="workspace-shell artifact-shell"><header className="workspace-topbar"><button className="back-link" onClick={() => window.location.assign(`/projects/${projectId}`)}>← Screenplay</button><div><p className="eyebrow warm">STORY DEVELOPMENT</p><h1>Creative artifacts</h1></div><span className="save-state"><span className="status-dot" /> Versioned workspace</span></header><div className="artifact-grid"><aside className="artifact-nav"><div className="panel-label"><span>Artifacts</span><div className="artifact-add"><select value={newKind} onChange={event => setNewKind(event.target.value)} aria-label="New artifact kind">{artifactKinds.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><button className="mini-button" onClick={() => void addArtifact()}>＋ Add</button></div></div><label className="artifact-dependencies">Depends on<select multiple value={newDependencies.map(String)} onChange={event => setNewDependencies(Array.from(event.target.selectedOptions, option => Number(option.value)))} aria-label="Artifact dependencies">{artifacts.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select><small>Optional; dependent artifacts become stale after an approved revision.</small></label>{artifacts.length === 0 && <p className="empty-copy">No story artifacts yet. Create a brief, outline, character, or timeline.</p>}{artifacts.map(item => <button key={item.id} className={item.id === selectedId ? 'artifact-link selected' : 'artifact-link'} onClick={() => setSelectedId(item.id)}><span>{item.kind}</span><strong>{item.title}</strong>{item.stale && <em>STALE</em>}</button>)}</aside><main className="artifact-editor">{selected && draft ? <><div className="artifact-heading"><div><p className="eyebrow warm">{selected.kind.toUpperCase()} · VERSION {selected.version}</p><input value={draft.title} onChange={event => setDrafts(current => ({ ...current, [selected.id]: { ...draft, title: event.target.value } }))} onBlur={() => void save(selected)} aria-label="Artifact title" />{selected.stale && <p className="stale-warning">This artifact is stale because a dependency changed. Revise or regenerate it deliberately.</p>}</div><span className="save-state">Autosaves on blur</span></div><textarea className="artifact-content" value={draft.content} onChange={event => setDrafts(current => ({ ...current, [selected.id]: { ...draft, content: event.target.value } }))} onBlur={() => void save(selected)} aria-label="Artifact content" placeholder="Develop the next layer of the story…" /><section className="story-operation" aria-label="Typed story operation"><div className="panel-label"><span>Structured decision</span><span>Versioned operation</span></div>{operationOptions.length ? <><label>Operation<select value={operation} onChange={event => chooseOperation(event.target.value)} aria-label="Story operation">{operationOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{operation === 'set_logline' && <label>Logline<input value={operationDraft.text ?? ''} onChange={event => setOperationDraft(current => ({ ...current, text: event.target.value }))} aria-label="Operation logline" /></label>}{operation === 'add_beat' && <><label>Beat title<input value={operationDraft.title ?? ''} onChange={event => setOperationDraft(current => ({ ...current, title: event.target.value }))} aria-label="Beat title" /></label><label>Summary<textarea value={operationDraft.summary ?? ''} onChange={event => setOperationDraft(current => ({ ...current, summary: event.target.value }))} aria-label="Beat summary" /></label><label>Sequence<input type="number" min="1" value={operationDraft.sequence ?? '1'} onChange={event => setOperationDraft(current => ({ ...current, sequence: event.target.value }))} aria-label="Beat sequence" /></label></>}{operation === 'add_character_arc' && <><label>Character<input value={operationDraft.character ?? ''} onChange={event => setOperationDraft(current => ({ ...current, character: event.target.value }))} aria-label="Arc character" /></label><label>Want<input value={operationDraft.want ?? ''} onChange={event => setOperationDraft(current => ({ ...current, want: event.target.value }))} aria-label="Character want" /></label><label>Need<input value={operationDraft.need ?? ''} onChange={event => setOperationDraft(current => ({ ...current, need: event.target.value }))} aria-label="Character need" /></label></>}{operation === 'add_canon_rule' && <><label>Rule<textarea value={operationDraft.rule ?? ''} onChange={event => setOperationDraft(current => ({ ...current, rule: event.target.value }))} aria-label="Canon rule" /></label><label>Rationale<input value={operationDraft.rationale ?? ''} onChange={event => setOperationDraft(current => ({ ...current, rationale: event.target.value }))} aria-label="Canon rationale" /></label></>}<button className="button quiet" onClick={() => void submitOperation()}>Apply structured decision</button>{operationError && <p className="copilot-error">{operationError}</p>}</> : <p className="empty-copy">This artifact kind has no structured operation yet.</p>}</section></> : <div className="empty-script"><span>✦</span><h2>Build the story around the screenplay.</h2><p>Create editable artifacts that can be revised out of order.</p></div>}{error && <p className="copilot-error">{error}</p>}</main><aside className="context-panel"><CopilotPanel projectId={projectId} page={`/projects/${projectId}/studio`} artifact={selected?.kind ?? null} selection={selected?.title ?? null} /></aside></div></div>
}
