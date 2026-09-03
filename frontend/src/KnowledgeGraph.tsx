import { useEffect, useState } from 'react'
import { getKnowledgeGraph, KnowledgeGraph } from './api'
import CopilotPanel from './CopilotPanel'

type KnowledgeGraphProps = { projectId: number }

export default function KnowledgeGraphPage({ projectId }: KnowledgeGraphProps) {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void getKnowledgeGraph(projectId).then(setGraph).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load knowledge graph'))
  }, [projectId])

  if (error) return <main className="workspace-error"><p>{error}</p><a className="button primary" href={`/projects/${projectId}`}>Back to screenplay</a></main>
  if (!graph) return <main className="workspace-loading"><span className="status-dot" /> Loading project context…</main>
  const nodeLabel = new Map(graph.nodes.map(node => [node.id, node.label]))
  return <div className="workspace-shell context-shell"><header className="workspace-topbar"><a className="back-link" href={`/projects/${projectId}`}>← Screenplay</a><div><p className="eyebrow warm">PROJECT CONTEXT</p><h1>Knowledge graph</h1></div><span className="save-state">{graph.nodes.length} nodes · {graph.edges.length} links</span></header><div className="context-grid"><main className="graph-canvas"><div className="graph-intro"><p className="eyebrow warm">CANON & CONNECTIONS</p><h2>What the story knows.</h2><p>Nodes and relationships are project-scoped canonical context. Every change remains editable and versioned.</p></div>{graph.nodes.length === 0 ? <div className="graph-empty"><strong>No canonical nodes yet.</strong><span>Add characters, places, beats, or references as the story develops.</span></div> : <section className="graph-nodes">{graph.nodes.map(node => <article className="graph-node" key={node.id}><span>{node.kind}</span><h3>{node.label}</h3>{node.description && <p>{node.description}</p>}<small>v{node.version}</small></article>)}</section>}<section className="graph-edges"><p className="eyebrow">RELATIONSHIPS / {graph.edges.length}</p>{graph.edges.map(edge => <div className="graph-edge" key={edge.id}><strong>{nodeLabel.get(edge.source_node_id) ?? `#${edge.source_node_id}`}</strong><span>— {edge.relation} →</span><strong>{nodeLabel.get(edge.target_node_id) ?? `#${edge.target_node_id}`}</strong></div>)}</section></main><aside className="context-panel"><CopilotPanel projectId={projectId} /></aside></div></div>
}
