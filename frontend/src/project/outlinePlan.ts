import type { Beat, BeatFields } from '../storyApi'
import { byPosition } from './order'

export type BeatChange = { beat: Beat; fields: Pick<BeatFields, 'act_id' | 'position'> }

/** The column a beat shows in: its act when that act is on the board, else the unassigned column (null). */
export function columnOf(beat: Beat, actIds: ReadonlySet<number>): number | null {
  return beat.act_id !== null && actIds.has(beat.act_id) ? beat.act_id : null
}

/** The ordered beats of one column. */
export function beatsIn(beats: Beat[], actId: number | null, actIds: ReadonlySet<number>): Beat[] {
  return byPosition(beats.filter(beat => columnOf(beat, actIds) === actId))
}

/**
 * Plan moving a beat to `index` in the column `actId` (null = unassigned): the minimal set of PATCHes
 * that leaves both the source and target columns with contiguous positions.
 */
export function planBeatMove(beats: Beat[], beatId: number, actId: number | null, index: number, actIds: ReadonlySet<number>): BeatChange[] {
  const moving = beats.find(beat => beat.id === beatId)
  if (!moving) return []
  const source = columnOf(moving, actIds)
  const others = beats.filter(beat => beat.id !== beatId)
  const target = beatsIn(others, actId, actIds)
  target.splice(Math.max(0, Math.min(index, target.length)), 0, moving)
  const changes: BeatChange[] = []
  target.forEach((beat, position) => {
    const fields: BeatChange['fields'] = {}
    if (beat.id === beatId && source !== actId) fields.act_id = actId
    if (beat.position !== position || (beat.id === beatId && source !== actId)) fields.position = position
    if (Object.keys(fields).length) changes.push({ beat, fields })
  })
  if (source !== actId) {
    beatsIn(others, source, actIds).forEach((beat, position) => {
      if (beat.position !== position) changes.push({ beat, fields: { position } })
    })
  }
  return changes
}
