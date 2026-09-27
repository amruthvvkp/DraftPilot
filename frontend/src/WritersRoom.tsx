import { useEffect, useMemo, useState } from 'react'
import {
  AgentProposal,
  approveAgentProposal,
  cancelWorkflowRun,
  getAgentProposals,
  getInsights,
  getProjectWorkspace,
  giveFeedback,
  Insights,
  JsonSchema,
  listRoomWorkflows,
  listWorkflowRuns,
  ProjectWorkspace,
  rejectAgentProposal,
  RoomWorkflow,
  rollbackAgentProposal,
  startRoomWorkflow,
  subscribeProjectEvents,
  WorkflowRun,
} from './api'
import RoomChat from './RoomChat'
import './room.css'

type Json = Record<string, unknown>
type TrailStep = { step: string; role: string; duration_ms: number; output: unknown }

const ROLE_LABELS: Record<string, string> = {
  story_editor: 'Story editor', script_doctor: 'Script doctor', scene_writer: 'Scene writer', brainstormer: 'Brainstormer',
  story_architect: 'Story architect', character_specialist: 'Character specialist', audience_evaluator: 'Audience evaluator',
  coverage_reader: 'Coverage reader', continuity_supervisor: 'Continuity supervisor',
}
const HIDDEN_PARAMS = new Set(['beats', 'outline_artifact_id'])
const ACTIVE = new Set(['queued', 'running'])

/** Return a field's default value in the form's editing representation. */
function initialValue(schema: JsonSchema): string | string[] {
  if (schema.type === 'array') return Array.isArray(schema.default) ? (schema.default as unknown[]).map(String) : []
  return schema.default === undefined || schema.default === null ? '' : String(schema.default)
}

/** Convert the form's editing values back into typed workflow parameters. */
function toParams(schema: JsonSchema, values: Record<string, string | string[]>): Json {
  const params: Json = {}
  for (const [name, field] of Object.entries(schema.properties ?? {})) {
    const value = values[name]
    if (value === undefined || HIDDEN_PARAMS.has(name)) continue
    if (field.type === 'integer') { if (value !== '') params[name] = Number(value) }
    else if (field.type === 'array') {
      const items = (Array.isArray(value) ? value : String(value).split('\n')).map(item => item.trim()).filter(Boolean)
      params[name] = field.items?.type === 'integer' ? items.map(Number) : items
    } else if (value !== '') params[name] = value
  }
  return params
}

export default function WritersRoom({ projectId }: { projectId: number }) {
  const [workflows, setWorkflows] = useState<RoomWorkflow[]>([])
  const [selectedKey, setSelectedKey] = useState('')
  const [values, setValues] = useState<Record<string, string | string[]>>({})
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [openRunId, setOpenRunId] = useState<number | null>(null)
  const [proposals, setProposals] = useState<AgentProposal[]>([])
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [rated, setRated] = useState<Record<number, 1 | -1>>({})

  const selected = workflows.find(workflow => workflow.key === selectedKey)
  const scenes = useMemo(() => workspace?.scenes ?? [], [workspace])

  async function refreshRuns(): Promise<void> {
    const [nextRuns, nextProposals] = await Promise.all([listWorkflowRuns(projectId), getAgentProposals(projectId)])
    setRuns(nextRuns.filter(run => run.kind === 'room_workflow').sort((a, b) => b.id - a.id))
    setProposals(nextProposals)
    setInsights(await getInsights(projectId).catch(() => null))
  }

  useEffect(() => {
    Promise.all([listRoomWorkflows(projectId), getProjectWorkspace(projectId)]).then(([nextWorkflows, nextWorkspace]) => {
      setWorkflows(nextWorkflows)
      setWorkspace(nextWorkspace)
      if (nextWorkflows[0]) choose(nextWorkflows[0])
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load the writers’ room'))
    void refreshRuns().catch(() => undefined)
    return subscribeProjectEvents(projectId, event => {
      if (['run.changed', 'workflow.progress', 'proposal.changed'].includes(event.kind)) void refreshRuns().catch(() => undefined)
    })
  }, [projectId])

  function choose(workflow: RoomWorkflow): void {
    setSelectedKey(workflow.key)
    setValues(Object.fromEntries(Object.entries(workflow.params_schema.properties ?? {}).map(([name, field]) => [name, initialValue(field)])))
  }

  async function start(): Promise<void> {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      const run = await startRoomWorkflow(projectId, selected.key, toParams(selected.params_schema, values))
      setOpenRunId(run.id)
      await refreshRuns()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to start the workflow')
    } finally { setBusy(false) }
  }

  async function act(action: (projectId: number, id: number) => Promise<unknown>, id: number): Promise<void> {
    setError('')
    try { await action(projectId, id); await refreshRuns() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to update the proposal') }
  }

  async function rate(runId: number, rating: 1 | -1): Promise<void> {
    try { await giveFeedback(projectId, { workflow_run_id: runId }, rating); setRated(current => ({ ...current, [runId]: rating })); await refreshRuns() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save feedback') }
  }

  const required = new Set(selected?.params_schema.required ?? [])
  const missing = selected ? [...required].some(name => { const value = values[name]; return Array.isArray(value) ? value.length === 0 : !value }) : true

  return <div className="room-page">
    <header className="room-head">
      <div><a className="room-back" href={`/projects/${projectId}`}>← Workspace</a> <a className="room-back" href={`/projects/${projectId}/twin`}>Story twin ↗</a><p className="eyebrow warm">WRITERS’ ROOM</p><h1>Put the room to work</h1><p>Each workflow is a team of agents with a critique loop or a panel. Anything that would change your script or story arrives as a proposal you approve.</p></div>
    </header>
    {error && <p className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    <div className="room-grid">
      <section className="room-launcher" aria-label="Room workflows">
        <div className="room-workflow-list" role="tablist">{workflows.map(workflow => <button key={workflow.key} role="tab" aria-selected={workflow.key === selectedKey} className={workflow.key === selectedKey ? 'active' : ''} onClick={() => choose(workflow)}><strong>{workflow.label}</strong><small>{workflow.description}</small><span className={workflow.proposes ? 'badge proposes' : 'badge report'}>{workflow.proposes ? 'Proposes changes' : 'Report'}</span></button>)}</div>
        {selected && <form className="room-form" onSubmit={event => { event.preventDefault(); void start() }}>
          <p className="room-roles">With {selected.roles.map(role => ROLE_LABELS[role] ?? role).join(' · ')}</p>
          {Object.entries(selected.params_schema.properties ?? {}).filter(([name]) => !HIDDEN_PARAMS.has(name)).map(([name, field]) => <ParamField key={name} name={name} field={field} required={required.has(name)} value={values[name] ?? ''} scenes={scenes} onChange={value => setValues(current => ({ ...current, [name]: value }))} />)}
          {selected.key === 'draft_scenes' && <p className="helper">Drafts the beats of your Outline artifact (run “Notes → outline” first, and approve it).</p>}
          <button className="button primary" type="submit" disabled={busy || missing}>{busy ? 'Starting…' : `Start ${selected.label.toLowerCase()}`}</button>
        </form>}
      </section>
      <div className="room-side"><RoomChat projectId={projectId} />
      <section className="room-runs" aria-label="Room runs">
        <p className="eyebrow">RUNS / {runs.length}</p>
        {runs.length === 0 && <p className="empty-copy">No room runs yet. Pick a workflow and start one; you can leave the page while it works.</p>}
        {runs.map(run => <RunCard key={run.id} run={run} open={openRunId === run.id} onToggle={() => setOpenRunId(openRunId === run.id ? null : run.id)} proposals={proposals.filter(proposal => proposal.run_id === run.id)} onCancel={() => void act(cancelWorkflowRun, run.id)} onApprove={id => void act(approveAgentProposal, id)} onReject={id => void act(rejectAgentProposal, id)} onRollback={id => void act(rollbackAgentProposal, id)} rated={rated[run.id]} onRate={rating => void rate(run.id, rating)} label={workflows.find(workflow => workflow.key === run.input?.workflow)?.label ?? String(run.input?.workflow ?? 'Workflow')} />)}
        {insights && Object.keys(insights.workflows).length > 0 && <InsightsTable insights={insights} labels={Object.fromEntries(workflows.map(workflow => [workflow.key, workflow.label]))} />}
      </section></div>
    </div>
  </div>
}

const pct = (value: number | null) => value === null ? '—' : `${Math.round(value * 100)}%`

function InsightsTable({ insights, labels }: { insights: Insights; labels: Record<string, string> }) {
  return <div className="room-insights" aria-label="Room usefulness"><p className="eyebrow">HOW USEFUL IS THE ROOM?</p>
    <table><thead><tr><th>Workflow</th><th title="Runs that finished">Runs</th><th title="Approved ÷ decided proposals">Accepted</th><th title="Agent-written blocks you kept unchanged">Kept</th><th>👍 / 👎</th><th title="Mean of accepted, kept and thumbs-up share">Useful</th><th>Avg time</th></tr></thead>
      <tbody>{Object.entries(insights.workflows).map(([key, row]) => <tr key={key}><td>{labels[key] ?? key}</td><td>{row.succeeded}/{row.runs}</td><td>{pct(row.acceptance)}</td><td>{pct(row.retention)}</td><td>{row.up} / {row.down}</td><td><strong>{pct(row.usefulness)}</strong></td><td>{row.mean_duration_s === null ? '—' : `${Math.round(row.mean_duration_s)} s`}</td></tr>)}</tbody></table>
    <small>“Kept” falls as you rewrite the room’s words — authorship moves back to you when you edit.</small>
  </div>
}

function ParamField({ name, field, required, value, scenes, onChange }: { name: string; field: JsonSchema; required: boolean; value: string | string[]; scenes: ProjectWorkspace['scenes']; onChange: (value: string | string[]) => void }) {
  const label = `${field.title ?? name}${required ? '' : ' (optional)'}`
  if (name === 'scene_id') return <label>{label}<select aria-label={field.title ?? name} value={String(value)} onChange={event => onChange(event.target.value)}><option value="">Choose a scene</option>{scenes.map((scene, index) => <option key={scene.id} value={scene.id}>{index + 1}. {scene.heading}</option>)}</select></label>
  if (name === 'scene_ids') return <label>{label}<select multiple aria-label={field.title ?? name} value={Array.isArray(value) ? value : []} onChange={event => onChange([...event.target.selectedOptions].map(option => option.value))}>{scenes.map((scene, index) => <option key={scene.id} value={scene.id}>{index + 1}. {scene.heading}</option>)}</select><small>Leave empty for the whole script.</small></label>
  if (field.type === 'integer') return <label>{label}<input type="number" aria-label={field.title ?? name} min={field.minimum} max={field.maximum} value={String(value)} onChange={event => onChange(event.target.value)} /></label>
  if (field.type === 'array') return <label>{label}<textarea aria-label={field.title ?? name} value={Array.isArray(value) ? value.join('\n') : value} onChange={event => onChange(event.target.value.split('\n'))} placeholder="One per line" /></label>
  const long = (field.maxLength ?? 0) > 300
  return <label>{label}{long ? <textarea aria-label={field.title ?? name} value={String(value)} onChange={event => onChange(event.target.value)} /> : <input aria-label={field.title ?? name} value={String(value)} onChange={event => onChange(event.target.value)} />}</label>
}

function RunCard({ run, label, open, proposals, rated, onToggle, onCancel, onApprove, onReject, onRollback, onRate }: { run: WorkflowRun; label: string; open: boolean; proposals: AgentProposal[]; rated?: 1 | -1; onToggle: () => void; onCancel: () => void; onApprove: (id: number) => void; onReject: (id: number) => void; onRollback: (id: number) => void; onRate: (rating: 1 | -1) => void }) {
  const result = (run.result ?? {}) as Json
  const trail = (Array.isArray(result.trail) ? result.trail : []) as TrailStep[]
  return <article className={`room-run ${run.status}`}>
    <button className="room-run-head" onClick={onToggle} aria-expanded={open}><strong>{label}</strong><span className={`run-status ${run.status}`}>{run.status}{ACTIVE.has(run.status) && trail.length ? ` · step ${trail.length}` : ''}</span><small>#{run.id}{run.created_at ? ` · ${new Date(run.created_at).toLocaleString()}` : ''}</small></button>
    {open && <div className="room-run-body">
      {trail.length > 0 && <ol className="room-trail">{trail.map((step, index) => <li key={index}><span>{ROLE_LABELS[step.role] ?? step.role}</span> {step.step}<small>{(step.duration_ms / 1000).toFixed(1)} s</small></li>)}{ACTIVE.has(run.status) && <li className="working">working…</li>}</ol>}
      {ACTIVE.has(run.status) && <button className="button quiet" onClick={onCancel}>Cancel run</button>}
      {run.error && <p className="error-text">{run.error}</p>}
      {run.status === 'succeeded' && <RunResult workflow={String(result.workflow ?? '')} result={result} />}
      {run.status === 'succeeded' && <div className="room-feedback"><span>Was this useful?</span><button className={rated === 1 ? 'chosen' : ''} aria-label="Helpful" aria-pressed={rated === 1} onClick={() => onRate(1)}>👍</button><button className={rated === -1 ? 'chosen' : ''} aria-label="Not helpful" aria-pressed={rated === -1} onClick={() => onRate(-1)}>👎</button>{Object.entries((result.checks ?? {}) as Record<string, number>).map(([name, value]) => <span className={`check ${value >= 0.5 ? 'pass' : 'fail'}`} key={name} title="Automatic check">{name.replace(/_/g, ' ')} {value === 1 || value === 0 ? (value ? '✓' : '✗') : value.toFixed(1)}</span>)}</div>}
      {proposals.length > 0 && <div className="room-proposals"><p className="eyebrow warm">FOR YOUR REVIEW</p>{proposals.map(proposal => <div className="room-proposal" key={proposal.id}><div><strong>{String(proposal.diff?.summary ?? `${proposal.target_kind} #${proposal.target_id}`)}</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div>{proposal.status === 'proposed' && <div className="proposal-actions"><button className="button primary" onClick={() => onApprove(proposal.id)}>Approve</button><button className="button quiet" onClick={() => onReject(proposal.id)}>Reject</button></div>}{proposal.status === 'approved' && <button className="button quiet" onClick={() => onRollback(proposal.id)}>Roll back</button>}</div>)}</div>}
    </div>}
  </article>
}

function RunResult({ workflow, result }: { workflow: string; result: Json }) {
  const get = <T,>(key: string): T => result[key] as T
  if (workflow === 'notes_to_outline') {
    const outline = get<{ logline: string; beats: { act: number; title: string; summary: string }[] }>('outline')
    const critique = get<{ score: number } | null>('critique')
    return <div className="room-result"><p className="logline">{outline.logline}</p><ol className="beats">{outline.beats.map((beat, index) => <li key={index}><small>ACT {beat.act}</small> <strong>{beat.title}</strong> — {beat.summary}</li>)}</ol>{critique && <p className="score">Script doctor: {critique.score}/10 after {String(result.rounds)} revision(s)</p>}</div>
  }
  if (workflow === 'brainstorm') {
    const shortlist = get<{ picks: { title: string; reason: string }[]; synthesis: string }>('shortlist')
    return <div className="room-result"><ol>{shortlist.picks.map(pick => <li key={pick.title}><strong>{pick.title}</strong> — {pick.reason}</li>)}</ol><p>{shortlist.synthesis}</p></div>
  }
  if (workflow === 'character_arcs') {
    return <div className="room-result">{get<Json[]>('arcs').map(arc => <div className="arc" key={String(arc.character)}><strong>{String(arc.character)}</strong><p><em>Wants</em> {String(arc.want)} · <em>Needs</em> {String(arc.need)}</p><p>{String(arc.arc_summary)}</p></div>)}</div>
  }
  if (workflow === 'rewrite_scene') {
    const critique = get<{ score: number } | null>('critique')
    return <div className="room-result"><pre className="fountain">{String(result.fountain)}</pre>{Boolean(result.rationale) && <p>{String(result.rationale)}</p>}{critique && <p className="score">Script doctor: {critique.score}/10</p>}</div>
  }
  if (workflow === 'draft_scenes') {
    return <div className="room-result">{get<Json[]>('scenes').map(scene => <pre className="fountain" key={String(scene.index)}>{String(scene.fountain)}</pre>)}</div>
  }
  if (workflow === 'audience_panel') {
    const summary = get<{ mean_engagement: number; recommend_rate: number; shared_sticking_points: string[] }>('summary')
    return <div className="room-result"><p className="score">Engagement {summary.mean_engagement}/10 · {Math.round(summary.recommend_rate * 100)}% would recommend</p>{summary.shared_sticking_points.length > 0 && <p>Shared sticking points: {summary.shared_sticking_points.join('; ')}</p>}{get<Json[]>('reactions').map(reaction => <div className="arc" key={String(reaction.persona)}><strong>{String(reaction.persona)}</strong> · {String(reaction.engagement)}/10{reaction.quote ? <p>“{String(reaction.quote)}”</p> : null}</div>)}</div>
  }
  if (workflow === 'coverage') {
    const coverage = get<Json>('coverage')
    return <div className="room-result"><p className="score">Verdict: {String(coverage.verdict).toUpperCase()}</p><p className="logline">{String(coverage.logline)}</p><dl className="grades">{['premise', 'structure', 'character', 'dialogue', 'pacing'].map(key => <div key={key}><dt>{key}</dt><dd>{String(coverage[key])}</dd></div>)}</dl><p>{String(coverage.synopsis)}</p></div>
  }
  if (workflow === 'continuity') {
    const issues = get<Json[]>('issues')
    return <div className="room-result">{issues.length === 0 ? <p>No continuity problems found.</p> : <ul>{issues.map((issue, index) => <li key={index}><small>{String(issue.kind).toUpperCase()} · scenes {(issue.scene_ids as number[]).join(', ') || '—'}</small> {String(issue.description)}{issue.suggestion ? <em> — {String(issue.suggestion)}</em> : null}</li>)}</ul>}</div>
  }
  return <pre>{JSON.stringify(result, null, 2)}</pre>
}
