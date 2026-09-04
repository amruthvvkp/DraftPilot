import { useEffect, useMemo, useState } from 'react'
import {
  ContextWorkflowSpec,
  getWorkflowRun,
  listArtifacts,
  listContextWorkflows,
  startContextWorkflow,
  StoryArtifact,
  WorkflowRun,
} from './api'

type ContextWorkflowPanelProps = { projectId: number }

export default function ContextWorkflowPanel({ projectId }: ContextWorkflowPanelProps) {
  const [workflows, setWorkflows] = useState<ContextWorkflowSpec[]>([])
  const [artifacts, setArtifacts] = useState<StoryArtifact[]>([])
  const [workflowKey, setWorkflowKey] = useState('')
  const [artifactId, setArtifactId] = useState('')
  const [instruction, setInstruction] = useState('')
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void Promise.all([listContextWorkflows(projectId), listArtifacts(projectId)]).then(([nextWorkflows, nextArtifacts]) => {
      setWorkflows(nextWorkflows)
      setArtifacts(nextArtifacts)
      setWorkflowKey(nextWorkflows[0]?.key ?? '')
      setArtifactId(String(nextArtifacts[0]?.id ?? ''))
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load context workflows'))
  }, [projectId])

  const selected = workflows.find(workflow => workflow.key === workflowKey)
  const compatibleArtifacts = useMemo(
    () => selected ? artifacts.filter(artifact => selected.input_artifact_kinds.includes(artifact.kind)) : [],
    [artifacts, selected],
  )

  useEffect(() => {
    if (compatibleArtifacts.length > 0 && !compatibleArtifacts.some(artifact => String(artifact.id) === artifactId)) {
      setArtifactId(String(compatibleArtifacts[0].id))
    }
  }, [artifactId, compatibleArtifacts])

  async function start(): Promise<void> {
    if (!selected || !artifactId || !instruction.trim()) return
    setBusy(true)
    setError('')
    setRun(null)
    try {
      const pending = await startContextWorkflow(projectId, selected.key, Number(artifactId), instruction.trim())
      setRun(pending)
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 500))
        const current = await getWorkflowRun(projectId, pending.id)
        setRun(current)
        if (current.status === 'succeeded' || current.status === 'failed' || current.status === 'cancelled') return
      }
      setError('The context run is still active; its result will remain available when you return.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to start context workflow')
    } finally {
      setBusy(false)
    }
  }

  const suggestion = typeof run?.result?.suggestion === 'string' ? run.result.suggestion : null
  const hasCitations = Array.isArray(run?.result?.citations)
  return <section className="context-workflows" aria-label="Context generation workflows">
    <div className="panel-label"><span>Context workflows</span><span className="context-badge">Review first</span></div>
    <p className="helper">Generate a cited suggestion for camera, lighting, palettes, references, or continuity. Canonical context is never changed automatically.</p>
    {error && <p className="error-text">{error}</p>}
    {workflows.length === 0 ? <p className="empty-copy">No context workflows are available.</p> : <>
      <label>Workflow<select value={workflowKey} onChange={event => setWorkflowKey(event.target.value)} aria-label="Context workflow">{workflows.map(workflow => <option value={workflow.key} key={workflow.key}>{workflow.label}</option>)}</select></label>
      <label>Source artifact<select value={artifactId} onChange={event => setArtifactId(event.target.value)} aria-label="Context workflow source">{compatibleArtifacts.map(artifact => <option value={artifact.id} key={artifact.id}>{artifact.title} · {artifact.kind}</option>)}</select></label>
      <label>Instruction<textarea value={instruction} onChange={event => setInstruction(event.target.value)} aria-label="Context workflow instruction" placeholder="What should the agent develop or check?" /></label>
      <button className="button primary" type="button" onClick={() => void start()} disabled={busy || !selected || compatibleArtifacts.length === 0 || !instruction.trim()}>{busy ? 'Generating…' : 'Generate review suggestion'}</button>
      {selected && compatibleArtifacts.length === 0 && <p className="helper">Create a compatible source artifact before running this workflow.</p>}
      {run && <div className="context-run" aria-live="polite"><small>RUN {run.id} · {run.status}</small>{suggestion && <p>{suggestion}</p>}{hasCitations && <small>Retrieved citations attached · output kind: {String(run.result?.output_kind ?? selected?.output_kind)}</small>}</div>}
    </>}
  </section>
}
