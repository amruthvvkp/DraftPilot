import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { approveAgentProposal, getWorkflowRun, rejectAgentProposal, type AgentProposal } from '../api'
import { keys } from '../data/queries'
import { roleLabel, toolLabel } from './labels'
import type { ToolEntry } from './reducer'

export type CardProps = { call: ToolEntry; args: Record<string, unknown>; result: unknown; projectId: number }

type Json = Record<string, unknown>
const isObject = (value: unknown): value is Json => typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown) => (typeof value === 'string' ? value : value === undefined || value === null ? '' : String(value))
const working = (call: ToolEntry) => call.status !== 'done'

/** Whether a tool result is (or carries) an agent proposal. */
export function proposalIn(result: unknown): AgentProposal | null {
  if (!isObject(result)) return null
  if (typeof result.id === 'number' && typeof result.status === 'string' && 'target_kind' in result) return result as unknown as AgentProposal
  if (isObject(result.proposal)) return proposalIn(result.proposal)
  return null
}

function CardShell({ call, title, children }: { call: ToolEntry; title?: string; children?: ReactNode }) {
  return <section className={`chat-card ${call.status}`} aria-label={title ?? toolLabel(call.name)}>
    <p className="chat-card-title">{title ?? toolLabel(call.name)}{working(call) && <span className="chat-card-working"> …</span>}</p>
    {children}
  </section>
}

/** Any tool: a chip, with arguments and result behind a disclosure. */
export function GenericCard({ call, args, result }: CardProps) {
  const done = call.status === 'done'
  return <details className="tool-call">
    <summary className={`tool-chip ${done ? 'done' : 'working'}`}>{toolLabel(call.name)}{args.role ? ` (${roleLabel(text(args.role))})` : ''}{done ? ' ✓' : '…'}</summary>
    <pre>{JSON.stringify(args, null, 2)}</pre>
    {result !== undefined && <pre>{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>}
  </details>
}

/** `plan`: the showrunner's checklist. */
export function PlanCard({ call, args, result }: CardProps) {
  const source = isObject(result) ? result : args
  const steps = Array.isArray(source.steps) ? source.steps.map(text) : []
  return <CardShell call={call} title="Plan">
    {text(source.goal) && <p className="chat-card-lead">{text(source.goal)}</p>}
    <ul className="chat-checklist">{steps.map((step, index) => {
      const done = step.startsWith('✓')
      return <li key={index} className={done ? 'done' : ''}><input type="checkbox" readOnly checked={done} aria-label={step.replace(/^✓\s*/, '')} /> {step.replace(/^✓\s*/, '')}</li>
    })}</ul>
  </CardShell>
}

const PROFILE_FIELDS = ['want', 'need', 'motive', 'objective', 'flaw', 'arc_summary'] as const

/** `read_character` / `create_story_entity` (character): a character card. */
export function CharacterCard({ call, args, result, projectId }: CardProps) {
  const row: Json = isObject(result) ? result : isObject(args.fields) ? args.fields : {}
  const timeline = Array.isArray(row.timeline) ? row.timeline.filter(isObject) : []
  return <CardShell call={call} title={call.name === 'create_story_entity' ? `New character: ${text(row.name)}` : `Character: ${text(row.name)}`}>
    {text(row.role) && <span className="badge role">{text(row.role)}</span>}
    {text(row.summary) && <p className="chat-card-lead">{text(row.summary)}</p>}
    <dl className="chat-facts">{PROFILE_FIELDS.filter(field => text(row[field])).map(field => <div key={field}><dt>{field === 'arc_summary' ? 'arc' : field}</dt><dd>{text(row[field])}</dd></div>)}</dl>
    {timeline.length > 0 && <ol className="chat-timeline">{timeline.map((event, index) => <li key={index}>{text(event.story_time) && <small>{text(event.story_time)} · </small>}{text(event.title)}</li>)}</ol>}
    {typeof row.id === 'number' && <Link to={`/projects/${projectId}/characters/${row.id}`}>Open {text(row.name)} ↗</Link>}
  </CardShell>
}

type OutlineAct = { title: string; beats: { title: string; summary: string }[] }

function outlineActs(args: Json, result: unknown): OutlineAct[] {
  if (isObject(result) && Array.isArray(result.acts)) {
    return result.acts.filter(isObject).map((act, index) => ({
      title: text(act.title) || `Act ${index + 1}`,
      beats: (Array.isArray(act.beats) ? act.beats : []).filter(isObject).map(beat => ({ title: text(beat.title), summary: text(beat.summary) })),
    }))
  }
  const beats = (Array.isArray(args.beats) ? args.beats : []).filter(isObject)
  const numbers = [...new Set(beats.map(beat => Number(beat.act) || 1))].sort((a, b) => a - b)
  return numbers.map(act => ({ title: `Act ${act}`, beats: beats.filter(beat => (Number(beat.act) || 1) === act).map(beat => ({ title: text(beat.title), summary: text(beat.summary) })) }))
}

/** `read_outline` / `propose_outline`: acts and their beats (a proposed outline also gets its approval card). */
export function OutlineCard(props: CardProps) {
  const { call, args, result, projectId } = props
  const acts = outlineActs(args, result)
  const proposal = proposalIn(result)
  return <CardShell call={call} title={call.name === 'propose_outline' ? 'Proposed outline' : 'Outline'}>
    {acts.length === 0 && <p className="empty-copy">No beats yet.</p>}
    {acts.map(act => <div className="chat-outline-act" key={act.title}><strong>{act.title}</strong>
      <ol>{act.beats.map((beat, index) => <li key={index}><b>{beat.title}</b>{beat.summary && ` — ${beat.summary}`}</li>)}</ol>
    </div>)}
    {proposal && <ProposalActions proposal={proposal} projectId={projectId} />}
    <Link to={`/projects/${projectId}/outline`}>Open the outline ↗</Link>
  </CardShell>
}

function ProposalActions({ proposal, projectId }: { proposal: AgentProposal; projectId: number }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState(proposal.status)
  const [error, setError] = useState('')
  async function decide(action: typeof approveAgentProposal): Promise<void> {
    setError('')
    try {
      const updated = await action(projectId, proposal.id)
      setStatus(updated.status)
      void queryClient.invalidateQueries({ queryKey: keys.project(projectId) })
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to decide the proposal') }
  }
  return <div className="chat-proposal-actions">
    <span className={`proposal-status ${status}`}>{status}</span>
    {status === 'proposed' && <>
      <button type="button" className="button primary" onClick={() => void decide(approveAgentProposal)}>Approve proposal</button>
      <button type="button" className="button quiet" onClick={() => void decide(rejectAgentProposal)}>Reject proposal</button>
    </>}
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </div>
}

/** `propose_*` or any result carrying a proposal: what it changes, with Approve / Reject. */
export function ProposalCard({ call, args, result, projectId }: CardProps) {
  const proposal = proposalIn(result)
  const summary = text(proposal?.diff?.summary) || text(args.summary) || (proposal ? `${proposal.target_kind} #${proposal.target_id}` : '')
  return <CardShell call={call} title={toolLabel(call.name)}>
    {summary && <p className="chat-card-lead">{summary}</p>}
    {proposal ? <ProposalActions proposal={proposal} projectId={projectId} /> : working(call) ? null : <pre>{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>}
  </CardShell>
}

const ACTIVE = new Set(['queued', 'running'])
type TrailStep = { step: string; role: string }

/** `start_room_workflow` / `start_evaluation`: follows the run until it is done. */
export function WorkflowCard({ call, args, result, projectId }: CardProps) {
  const started = isObject(result) && typeof result.id === 'number' ? result : null
  const runId = started ? Number(started.id) : 0
  const { data: run } = useQuery({
    queryKey: keys.run(projectId, runId),
    queryFn: () => getWorkflowRun(projectId, runId),
    enabled: runId > 0,
    refetchInterval: query => (query.state.data && !ACTIVE.has(query.state.data.status) ? false : 2000),
  })
  const status = run?.status ?? (text(started?.status) || 'starting')
  const runResult = isObject(run?.result) ? run.result : {}
  const trail = (Array.isArray(runResult.trail) ? runResult.trail : []).filter(isObject) as unknown as TrailStep[]
  const last = trail[trail.length - 1]
  const name = text(args.workflow) || (call.name === 'start_evaluation' ? 'evaluation' : 'workflow')
  return <CardShell call={call} title={`Room run: ${name.replace(/_/g, ' ')}`}>
    <p className="chat-card-lead"><span className={`run-status ${status}`}>{status}</span>{last && ACTIVE.has(status) && <span> · stage: {last.step.replace(/_/g, ' ')}</span>}</p>
    {trail.length > 0 && <ol className="room-trail">{trail.map((step, index) => <li key={index}><span>{roleLabel(step.role)}</span> {step.step}</li>)}</ol>}
    {run?.error && <p className="error-text">{run.error}</p>}
    {runId > 0 && <Link to={`/projects/${projectId}/room`}>Review in the writers’ room ↗</Link>}
  </CardShell>
}

/** `consult` / `consult_many`: who the showrunner asked, and their answers. */
export function SpecialistCard({ call, args, result }: CardProps) {
  const requests = call.name === 'consult_many' ? (Array.isArray(args.requests) ? args.requests.filter(isObject) : []) : [args]
  const answers = Array.isArray(result) ? result.map(text) : result === undefined ? [] : [text(result)]
  return <CardShell call={call} title={requests.length > 1 ? 'Consulted specialists' : 'Consulted a specialist'}>
    <div className="chat-chips">{requests.map((request, index) => <details key={index} className="specialist">
      <summary className={`tool-chip ${answers[index] !== undefined ? 'done' : 'working'}`}>{roleLabel(text(request.role))}{answers[index] !== undefined ? ' ✓' : '…'}</summary>
      <p><em>Brief:</em> {text(request.brief)}</p>
      {answers[index] && <p>{answers[index]}</p>}
    </details>)}</div>
  </CardShell>
}

/** `create_scene` / `write_scene`: the scene, with a link that opens it in the script. */
export function SceneCard({ call, args, result, projectId }: CardProps) {
  const scene = isObject(result) ? result : {}
  const sceneId = typeof scene.id === 'number' ? scene.id : typeof args.scene_id === 'number' ? args.scene_id : null
  const heading = text(scene.heading) || text(args.heading) || 'Scene'
  return <CardShell call={call} title={call.name === 'create_scene' ? `New scene: ${heading}` : `Rewrote: ${heading}`}>
    {text(args.fountain) && <pre className="fountain">{text(args.fountain).slice(0, 1200)}</pre>}
    {sceneId !== null && call.status === 'done' && <Link to={`/projects/${projectId}?scene=${sceneId}`}>Open {heading} ↗</Link>}
  </CardShell>
}
