import { useEffect, useState } from 'react'
import { approveTimelineProposal, createTimelineProposal, listTimelineProposals, ProjectWorkspace, rejectTimelineProposal, TimelineProposal } from './api'
import CopilotPanel from './CopilotPanel'
import './timeline.css'

type TimelineProps = { projectId: number; screenplayId: number; workspace: ProjectWorkspace }

function duration(body: string): number {
  return Math.max(30, Math.round(body.split(/\s+/).filter(Boolean).length / 2))
}

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

export default function Timeline({ projectId, screenplayId, workspace }: TimelineProps) {
  const [orderedIds, setOrderedIds] = useState(() => workspace.scenes.map(scene => scene.id))
  const [draggingId, setDraggingId] = useState<number | null>(null)
  const [proposal, setProposal] = useState<TimelineProposal | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void listTimelineProposals(projectId, screenplayId).then(proposals => {
      const pending = proposals.find(item => item.status === 'proposed')
      if (pending) {
        setProposal(pending)
        setOrderedIds(pending.proposed_scene_ids)
      }
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load timeline proposals'))
  }, [projectId, screenplayId])

  function move(sceneId: number, direction: -1 | 1): void {
    const index = orderedIds.indexOf(sceneId)
    const target = index + direction
    if (index < 0 || target < 0 || target >= orderedIds.length) return
    const next = [...orderedIds]
    ;[next[index], next[target]] = [next[target], next[index]]
    setOrderedIds(next)
    setProposal(null)
  }

  function drop(targetId: number): void {
    if (draggingId === null || draggingId === targetId) return
    const next = orderedIds.filter(id => id !== draggingId)
    next.splice(next.indexOf(targetId), 0, draggingId)
    setOrderedIds(next)
    setDraggingId(null)
    setProposal(null)
  }

  async function propose(): Promise<void> {
    setError('')
    try {
      const durations = Object.fromEntries(workspace.scenes.map(scene => [scene.id, duration(scene.body)]))
      setProposal(await createTimelineProposal(projectId, screenplayId, orderedIds, durations))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create timeline proposal')
    }
  }

  async function approve(): Promise<void> {
    if (!proposal) return
    setError('')
    try {
      setProposal(await approveTimelineProposal(projectId, screenplayId, proposal.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to approve timeline proposal')
    }
  }

  async function reject(): Promise<void> {
    if (!proposal) return
    setError('')
    try {
      setProposal(await rejectTimelineProposal(projectId, screenplayId, proposal.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to reject timeline proposal')
    }
  }

  const byId = new Map(workspace.scenes.map(scene => [scene.id, scene]))
  const actById = new Map(workspace.acts.map(act => [act.id, act]))
  const timingById = new Map<number, { start: number; end: number }>()
  let offset = 0
  for (const sceneId of orderedIds) {
    const scene = byId.get(sceneId)
    if (!scene) continue
    const end = offset + duration(scene.body)
    timingById.set(sceneId, { start: offset, end })
    offset = end
  }
  const charactersByScene = (sceneId: number): string[] => [...new Set(
    (workspace.blocks[sceneId] ?? [])
      .filter(block => block.element_type === 'character' && block.text.trim())
      .map(block => block.text.trim()),
  )]
  const actLanes = [...new Map(orderedIds.map(sceneId => {
    const scene = byId.get(sceneId)
    const act = scene ? actById.get(scene.act_id) : undefined
    return [scene?.act_id ?? sceneId, { label: act?.title || `Act ${(act?.position ?? 0) + 1}`, sceneIds: orderedIds.filter(id => byId.get(id)?.act_id === scene?.act_id) }]
  })).values()]
  const characterLaneMap = new Map<string, number[]>()
  for (const sceneId of orderedIds) for (const character of charactersByScene(sceneId)) characterLaneMap.set(character, [...(characterLaneMap.get(character) ?? []), sceneId])
  return <section className="timeline-board" aria-label="Screenplay timeline">
    <div className="timeline-head"><div><p className="eyebrow warm">TIMELINE / REORDER</p><h2>Shape the rhythm.</h2><p>Drag scenes or use the keyboard controls. Nothing changes until approved.</p></div><button className="button primary" onClick={() => void propose()} disabled={!orderedIds.length}>Review reorder</button></div>
    {error && <div className="notice">{error}</div>}
    <div className="time-ruler"><span>00:00</span><span>{clock(Math.round(offset / 4))}</span><span>{clock(Math.round(offset / 2))}</span><span>{clock(Math.round(offset * 3 / 4))}</span><span>{clock(offset)}</span></div>
    <section className="timeline-lanes" aria-label="Act and character lanes"><div className="lane-group"><p className="eyebrow warm">ACT LANES</p>{actLanes.map(lane => <div className="timeline-lane-row" key={lane.label}><strong>{lane.label}</strong><div>{lane.sceneIds.map(sceneId => <span className="lane-scene" key={sceneId}>{String(orderedIds.indexOf(sceneId) + 1).padStart(2, '0')}</span>)}</div></div>)}</div>{characterLaneMap.size > 0 && <div className="lane-group"><p className="eyebrow warm">CHARACTER LANES</p>{[...characterLaneMap.entries()].map(([character, sceneIds]) => <div className="timeline-lane-row" key={character}><strong>{character}</strong><div>{sceneIds.map(sceneId => <span className="lane-scene character" key={sceneId}>{String(orderedIds.indexOf(sceneId) + 1).padStart(2, '0')}</span>)}</div></div>)}</div>}</section>
    <div className="timeline-lane">{orderedIds.map((sceneId, index) => { const scene = byId.get(sceneId); const timing = timingById.get(sceneId); if (!scene || !timing) return null; const characters = charactersByScene(sceneId); return <article className="timeline-card" draggable onDragStart={() => setDraggingId(sceneId)} onDragOver={event => event.preventDefault()} onDrop={() => drop(sceneId)} key={sceneId}><span className="timeline-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{scene.heading}</strong><small>{clock(timing.start)}–{clock(timing.end)} · {duration(scene.body)} sec estimated · {actById.get(scene.act_id)?.title || `Act ${(actById.get(scene.act_id)?.position ?? 0) + 1}`}{characters.length ? ` · ${characters.join(', ')}` : ''}</small><small>{scene.body || 'No scene action yet.'}</small></div><div className="timeline-controls"><button aria-label={`Move ${scene.heading} earlier`} onClick={() => move(sceneId, -1)} disabled={index === 0}>↑</button><button aria-label={`Move ${scene.heading} later`} onClick={() => move(sceneId, 1)} disabled={index === orderedIds.length - 1}>↓</button></div></article> })}</div>
    {proposal && <div className="proposal-card"><div><p className="eyebrow warm">{proposal.status.toUpperCase()} PROPOSAL</p><strong>{Math.round(proposal.total_runtime_seconds / 60)} min projected runtime</strong><p>Dependent timeline artifacts will be marked stale after approval.</p></div><div>{proposal.status === 'proposed' && <><button className="button quiet" onClick={() => void reject()}>Reject</button><button className="button primary" onClick={() => void approve()}>Approve reorder</button></>}</div></div>}
    <aside className="timeline-copilot"><CopilotPanel projectId={projectId} page={`/projects/${projectId}/timeline`} artifact="timeline" selection={proposal ? `${proposal.proposed_scene_ids.length} scenes` : null} /></aside>
  </section>
}
