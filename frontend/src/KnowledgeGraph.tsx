import { useEffect, useState } from 'react'
import { createKnowledgeEdge, createKnowledgeNode, deleteKnowledgeEdge, getKnowledgeGraph, KnowledgeGraph, updateKnowledgeNode } from './api'
import CopilotPanel from './CopilotPanel'
import ProjectReferences from './ProjectReferences'

type KnowledgeGraphProps = { projectId: number }

function GraphNode({ projectId, node, onSaved }: { projectId: number; node: KnowledgeGraph['nodes'][number]; onSaved: (node: KnowledgeGraph['nodes'][number]) => void }) {
  const [label, setLabel] = useState(node.label)
  const [description, setDescription] = useState(node.description ?? '')
  const [saving, setSaving] = useState(false)

  async function save(): Promise<void> {
    if (label === node.label && description === (node.description ?? '')) return
    setSaving(true)
    try { onSaved(await updateKnowledgeNode(projectId, node.id, node.version, { label: label.trim(), description: description.trim() || null })) }
    finally { setSaving(false) }
  }

  return <article className="graph-node"><span>{node.kind}</span><input value={label} onChange={event => setLabel(event.target.value)} onBlur={() => void save()} aria-label={`Edit ${node.label} label`} /><textarea value={description} onChange={event => setDescription(event.target.value)} onBlur={() => void save()} aria-label={`Edit ${node.label} description`} /><small>{saving ? 'saving…' : `v${node.version}`}</small></article>
}

export default function KnowledgeGraphPage({ projectId }: KnowledgeGraphProps) {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null)
  const [error, setError] = useState('')
  const [kind, setKind] = useState(new URLSearchParams(window.location.search).get('kind') ?? 'character')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [sourceNode, setSourceNode] = useState('')
  const [targetNode, setTargetNode] = useState('')
  const [relation, setRelation] = useState('relates_to')

  async function addNode(): Promise<void> {
    if (!label.trim()) return
    setSaving(true)
    setError('')
    try {
      await createKnowledgeNode(projectId, kind, label.trim(), description.trim())
      setGraph(await getKnowledgeGraph(projectId))
      setLabel('')
      setDescription('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to add context node') }
    finally { setSaving(false) }
  }

  async function addEdge(): Promise<void> {
    if (!sourceNode || !targetNode || sourceNode === targetNode || !relation.trim()) return
    setSaving(true)
    setError('')
    try {
      await createKnowledgeEdge(projectId, Number(sourceNode), Number(targetNode), relation.trim())
      setGraph(await getKnowledgeGraph(projectId))
      setSourceNode('')
      setTargetNode('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to add relationship') }
    finally { setSaving(false) }
  }
  async function removeEdge(edgeId: number): Promise<void> {
    setSaving(true)
    setError('')
    try { await deleteKnowledgeEdge(projectId, edgeId); setGraph(current => current ? { ...current, edges: current.edges.filter(edge => edge.id !== edgeId) } : current) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to remove relationship') }
    finally { setSaving(false) }
  }

  useEffect(() => {
    void getKnowledgeGraph(projectId).then(setGraph).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load knowledge graph'))
  }, [projectId])

  if (error) return <main className="workspace-error"><p>{error}</p><a className="button primary" href={`/projects/${projectId}`}>Back to screenplay</a></main>
  if (!graph) return <main className="workspace-loading"><span className="status-dot" /> Loading project context…</main>
  const nodeLabel = new Map(graph.nodes.map(node => [node.id, node.label]))
  return <div className="workspace-shell context-shell"><header className="workspace-topbar"><a className="back-link" href={`/projects/${projectId}`}>← Screenplay</a><div><p className="eyebrow warm">PROJECT CONTEXT</p><h1>Knowledge graph</h1></div><span className="save-state">{graph.nodes.length} nodes · {graph.edges.length} links</span></header><div className="context-grid"><main className="graph-canvas"><div className="graph-intro"><p className="eyebrow warm">CANON & CONNECTIONS</p><h2>What the story knows.</h2><p>Nodes and relationships are project-scoped canonical context. Every change remains editable and versioned.</p></div><ProjectReferences projectId={projectId} /><form className="context-node-form" onSubmit={event => { event.preventDefault(); void addNode() }}><div><p className="eyebrow warm">ADD CANONICAL CONTEXT</p><label>Type<select value={kind} onChange={event => setKind(event.target.value)} aria-label="Context node type"><option value="character">Character</option><option value="place">Place</option><option value="beat">Beat</option><option value="reference_scene">Reference scene</option><option value="director">Director</option><option value="film">Film</option><option value="style">Style</option><option value="camera">Camera</option><option value="lighting">Lighting</option><option value="color_palette">Color palette</option></select></label><label>Label<input value={label} onChange={event => setLabel(event.target.value)} aria-label="Context node label" placeholder="e.g. The lantern keeper" /></label><label>Description<textarea value={description} onChange={event => setDescription(event.target.value)} aria-label="Context node description" placeholder="What should the studio remember?" /></label></div><button className="button primary" type="submit" disabled={saving || !label.trim()}>{saving ? 'Adding…' : 'Add context'}</button></form><form className="context-edge-form" onSubmit={event => { event.preventDefault(); void addEdge() }}><p className="eyebrow warm">LINK CONTEXT</p><label>From<select value={sourceNode} onChange={event => setSourceNode(event.target.value)} aria-label="Relationship source"><option value="">Choose node</option>{graph.nodes.map(node => <option value={node.id} key={node.id}>{node.label}</option>)}</select></label><label>Relation<input value={relation} onChange={event => setRelation(event.target.value)} aria-label="Relationship type" /></label><label>To<select value={targetNode} onChange={event => setTargetNode(event.target.value)} aria-label="Relationship target"><option value="">Choose node</option>{graph.nodes.map(node => <option value={node.id} key={node.id}>{node.label}</option>)}</select></label><button className="button quiet" type="submit" disabled={saving || !sourceNode || !targetNode || sourceNode === targetNode}>Link nodes</button></form>{graph.nodes.length === 0 ? <div className="graph-empty"><strong>No canonical nodes yet.</strong><span>Add characters, places, beats, or references as the story develops.</span></div> : <section className="graph-nodes">{graph.nodes.map(node => <GraphNode key={node.id} projectId={projectId} node={node} onSaved={updated => setGraph(current => current ? { ...current, nodes: current.nodes.map(item => item.id === updated.id ? updated : item) } : current)} />)}</section>}<section className="graph-edges"><p className="eyebrow">RELATIONSHIPS / {graph.edges.length}</p>{graph.edges.map(edge => <div className="graph-edge" key={edge.id}><strong>{nodeLabel.get(edge.source_node_id) ?? `#${edge.source_node_id}`}</strong><span>— {edge.relation} →</span><strong>{nodeLabel.get(edge.target_node_id) ?? `#${edge.target_node_id}`}</strong><button className="mini-button" aria-label={`Delete relationship ${edge.relation}`} onClick={() => void removeEdge(edge.id)} disabled={saving}>Remove</button></div>)}</section></main><aside className="context-panel"><CopilotPanel projectId={projectId} page={`/projects/${projectId}/context`} artifact="knowledge_graph" selection={kind} /></aside></div></div>
}
