import { useEffect, useState } from 'react'
import CopilotPanel from './CopilotPanel'
import { createArtifact, listArtifacts, StoryArtifact, updateArtifact } from './api'

type ArtifactStudioProps = { projectId: number }

export default function ArtifactStudio({ projectId }: ArtifactStudioProps) {
  const [artifacts, setArtifacts] = useState<StoryArtifact[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Record<number, { title: string; content: string }>>({})
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
    try { const item = await createArtifact(projectId, 'brief', 'New story artifact'); setArtifacts(current => [...current, item]); setSelectedId(item.id); setDrafts(current => ({ ...current, [item.id]: { title: item.title, content: item.content } })) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create story artifact') }
  }

  async function save(item: StoryArtifact): Promise<void> {
    const draft = drafts[item.id]
    if (!draft || (draft.title === item.title && draft.content === item.content)) return
    try { await updateArtifact(projectId, item.id, item.version, draft); await refresh() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save story artifact') }
  }

  const selected = artifacts.find(item => item.id === selectedId)
  const draft = selected ? drafts[selected.id] : undefined
  return <div className="workspace-shell artifact-shell"><header className="workspace-topbar"><button className="back-link" onClick={() => window.location.assign(`/projects/${projectId}`)}>← Screenplay</button><div><p className="eyebrow warm">STORY DEVELOPMENT</p><h1>Creative artifacts</h1></div><span className="save-state"><span className="status-dot" /> Versioned workspace</span></header><div className="artifact-grid"><aside className="artifact-nav"><div className="panel-label"><span>Artifacts</span><button className="mini-button" onClick={() => void addArtifact()}>＋ Add</button></div>{artifacts.length === 0 && <p className="empty-copy">No story artifacts yet. Create a brief, outline, character, or timeline.</p>}{artifacts.map(item => <button key={item.id} className={item.id === selectedId ? 'artifact-link selected' : 'artifact-link'} onClick={() => setSelectedId(item.id)}><span>{item.kind}</span><strong>{item.title}</strong>{item.stale && <em>STALE</em>}</button>)}</aside><main className="artifact-editor">{selected && draft ? <><div className="artifact-heading"><div><p className="eyebrow warm">{selected.kind.toUpperCase()} · VERSION {selected.version}</p><input value={draft.title} onChange={event => setDrafts(current => ({ ...current, [selected.id]: { ...draft, title: event.target.value } }))} onBlur={() => void save(selected)} aria-label="Artifact title" />{selected.stale && <p className="stale-warning">This artifact is stale because a dependency changed. Revise or regenerate it deliberately.</p>}</div><span className="save-state">Autosaves on blur</span></div><textarea className="artifact-content" value={draft.content} onChange={event => setDrafts(current => ({ ...current, [selected.id]: { ...draft, content: event.target.value } }))} onBlur={() => void save(selected)} aria-label="Artifact content" placeholder="Develop the next layer of the story…" /></> : <div className="empty-script"><span>✦</span><h2>Build the story around the screenplay.</h2><p>Create editable artifacts that can be revised out of order.</p></div>}{error && <p className="copilot-error">{error}</p>}</main><aside className="context-panel"><CopilotPanel projectId={projectId} /></aside></div></div>
}
