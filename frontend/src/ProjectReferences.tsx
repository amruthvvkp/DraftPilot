import { useEffect, useState, type JSX } from 'react'
import { deleteProjectReference, listProjectReferences, ProjectReference, updateProjectReference } from './api'

type ProjectReferencesProps = { projectId: number }

const kinds = ['film', 'director', 'style', 'reference_scene', 'camera', 'lighting', 'color_palette', 'location', 'other']

function ReferenceCard({ projectId, reference, onSaved, onDeleted }: { projectId: number; reference: ProjectReference; onSaved: (reference: ProjectReference) => void; onDeleted: (id: number) => void }): JSX.Element {
  const [draft, setDraft] = useState(reference)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function save(): Promise<void> {
    if (!draft.label.trim()) return
    if (draft.kind === reference.kind && draft.label === reference.label && (draft.url ?? '') === (reference.url ?? '') && (draft.note ?? '') === (reference.note ?? '')) return
    setSaving(true)
    setError('')
    try {
      const saved = await updateProjectReference(projectId, reference.id, reference.version, { kind: draft.kind, label: draft.label.trim(), url: draft.url?.trim() || null, note: draft.note?.trim() || null })
      setDraft(saved)
      onSaved(saved)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save reference') }
    finally { setSaving(false) }
  }

  async function remove(): Promise<void> {
    if (!window.confirm(`Remove ${reference.label}?`)) return
    setSaving(true)
    setError('')
    try { await deleteProjectReference(projectId, reference.id); onDeleted(reference.id) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to remove reference') }
    finally { setSaving(false) }
  }

  return <article className="reference-card"><div className="reference-card-head"><span className="eyebrow warm">{draft.kind.replace('_', ' ')}</span><small>v{reference.version}</small></div><label>Reference<input value={draft.label} onChange={event => setDraft({ ...draft, label: event.target.value })} onBlur={() => void save()} /></label><label>URL<input value={draft.url ?? ''} onChange={event => setDraft({ ...draft, url: event.target.value })} onBlur={() => void save()} placeholder="https://…" /></label><label>Note<textarea value={draft.note ?? ''} onChange={event => setDraft({ ...draft, note: event.target.value })} onBlur={() => void save()} placeholder="Why it belongs in the visual language" /></label><div className="reference-actions"><select aria-label={`Type for ${reference.label}`} value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value })}>{kinds.map(kind => <option value={kind} key={kind}>{kind.replace('_', ' ')}</option>)}</select><button type="button" className="mini-button" onClick={() => void save()} disabled={saving || !draft.label.trim()}>{saving ? 'Saving…' : 'Save'}</button><button type="button" className="mini-button danger" onClick={() => void remove()} disabled={saving}>Remove</button></div>{error && <small className="error-text">{error} Refresh to resolve a concurrent edit.</small>}</article>
}

export default function ProjectReferences({ projectId }: ProjectReferencesProps): JSX.Element {
  const [references, setReferences] = useState<ProjectReference[]>([])
  const [error, setError] = useState('')

  useEffect(() => { void listProjectReferences(projectId).then(setReferences).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load references')) }, [projectId])

  return <section className="references-panel"><div className="section-heading"><div><p className="eyebrow warm">CREATIVE REFERENCES</p><h3>Visual language</h3></div><span className="count">{references.length} saved</span></div>{error && <p className="error-text">{error}</p>}{references.length === 0 && !error && <p className="helper">No typed references yet. Add films, directors, styles, or production notes from the project setup.</p>}<div className="reference-list">{references.map(reference => <ReferenceCard key={reference.id} projectId={projectId} reference={reference} onSaved={saved => setReferences(current => current.map(item => item.id === saved.id ? saved : item))} onDeleted={id => setReferences(current => current.filter(item => item.id !== id))} />)}</div></section>
}
