import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { approveTimelineProposal, createTimelineProposal, listTimelineProposals, type ProjectWorkspace, rejectTimelineProposal, rollbackTimelineProposal, type TimelineProposal } from '../api'
import { errorMessage, keys } from '../data/queries'

const same = (a: number[], b: number[]): boolean => a.length === b.length && a.every((id, index) => id === b[index])

/** Estimate a scene's runtime: the workspace timing, else half a second per word (at least 30s). */
export function sceneSeconds(workspace: ProjectWorkspace, sceneId: number): number {
  const timing = workspace.timings?.find(row => row.scene_id === sceneId)
  if (timing && timing.estimated_duration_seconds > 0) return timing.estimated_duration_seconds
  const body = workspace.scenes.find(scene => scene.id === sceneId)?.body ?? ''
  return Math.max(30, Math.round(body.split(/\s+/).filter(Boolean).length / 2))
}

/** Fit a saved order to the current scenes: drop removed scenes, append new ones in script order. */
export function fitOrder(saved: number[], current: number[]): number[] {
  const known = new Set(current)
  const kept = saved.filter(id => known.has(id))
  const seen = new Set(kept)
  return [...kept, ...current.filter(id => !seen.has(id))]
}

/** Scene reorders as reversible timeline proposals: a drag proposes, Apply approves, Roll back restores. */
export function useSceneReorder(projectId: number, workspace: ProjectWorkspace | undefined, baseOrder: number[]) {
  const queryClient = useQueryClient()
  const screenplayId = workspace?.screenplay?.id ?? 0
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const proposals = useQuery({
    queryKey: keys.timelineProposals(projectId, screenplayId),
    queryFn: () => listTimelineProposals(projectId, screenplayId),
    enabled: screenplayId > 0,
  }).data ?? []
  const latest = [...proposals].sort((a, b) => b.id - a.id)
  // Only proposals made against the order on screen count; stale ones can't be applied anyway.
  const pending = latest.find(row => row.status === 'proposed' && same(row.original_scene_ids, baseOrder)) ?? null
  const applied = latest.find(row => row.status === 'approved' && same(row.proposed_scene_ids, baseOrder)) ?? null

  /** Run a proposal call, then refresh proposals (and the script when the order changed). */
  async function run(action: () => Promise<unknown>, fallback: string, changesScript = false): Promise<void> {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (reason) {
      setError(errorMessage(reason, fallback))
    } finally {
      setBusy(false)
      await queryClient.invalidateQueries({ queryKey: ['project', projectId, 'timeline-proposals'] })
      if (changesScript) await queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
    }
  }

  /** Propose `order` (replacing any pending proposal); proposing the current order just withdraws it. */
  function propose(order: number[]): Promise<void> {
    return run(async () => {
      if (pending) await rejectTimelineProposal(projectId, screenplayId, pending.id)
      if (same(order, baseOrder) || !workspace) return
      const durations = Object.fromEntries(order.map(id => [id, sceneSeconds(workspace, id)]))
      await createTimelineProposal(projectId, screenplayId, order, durations)
    }, 'Unable to propose the reorder')
  }

  return {
    pending,
    applied,
    error,
    busy,
    /** The order to show: the pending proposal's, else the script's. */
    order: pending?.proposed_scene_ids ?? baseOrder,
    propose,
    apply: (proposal: TimelineProposal) => run(() => approveTimelineProposal(projectId, screenplayId, proposal.id), 'Unable to apply the reorder', true),
    discard: (proposal: TimelineProposal) => run(() => rejectTimelineProposal(projectId, screenplayId, proposal.id), 'Unable to discard the reorder'),
    rollback: (proposal: TimelineProposal) => run(() => rollbackTimelineProposal(projectId, screenplayId, proposal.id), 'Unable to roll back the reorder', true),
  }
}
