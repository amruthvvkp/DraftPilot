import { describe, expect, it } from 'vitest'
import { type DualItem, dualAction, dualLayout, dualPairs, planDualToggle, speeches } from './dualDialogue'

const item = (element_type: string, is_dual = false, dual_group: number | null = null): DualItem => ({ element_type, is_dual, dual_group })

const TWO_SPEECHES = [item('action'), item('character'), item('dialogue'), item('character'), item('parenthetical'), item('dialogue'), item('action')]

describe('dual dialogue', () => {
  it('splits a scene into speeches', () => {
    expect(speeches(TWO_SPEECHES)).toEqual([{ start: 1, end: 3 }, { start: 3, end: 6 }])
  })

  it('pairs a speech with the one before it, across every block of both', () => {
    const plan = planDualToggle(TWO_SPEECHES, 5)!
    expect(plan.action).toBe('pair')
    expect(plan.changes.map(change => change.index)).toEqual([1, 2, 3, 4, 5])
    expect(new Set(plan.changes.map(change => `${change.is_dual}:${change.dual_group}`))).toEqual(new Set(['true:1']))
  })

  it('unpairs from either side of a pair', () => {
    const paired = TWO_SPEECHES.map((entry, index) => index >= 1 && index <= 5 ? item(entry.element_type, true, 4) : entry)
    expect(dualPairs(paired)).toEqual([{ left: { start: 1, end: 3 }, right: { start: 3, end: 6 } }])
    for (const index of [1, 2, 5]) {
      const plan = planDualToggle(paired, index)!
      expect(plan.action).toBe('unpair')
      expect(plan.changes.every(change => !change.is_dual && change.dual_group === null)).toBe(true)
      expect(plan.changes).toHaveLength(5)
    }
  })

  it('reads an older import that marked only the second cue as a pair', () => {
    const legacy = [item('character'), item('dialogue'), item('character', true), item('dialogue')]
    expect(dualPairs(legacy)).toHaveLength(1)
    expect(dualAction(legacy, 1)).toBe('unpair')
  })

  it('refuses to pair the first speech, a speech after an action, or outside a speech', () => {
    expect(dualAction(TWO_SPEECHES, 2)).toBeNull()
    expect(dualAction([item('character'), item('dialogue'), item('action'), item('character'), item('dialogue')], 4)).toBeNull()
    expect(dualAction(TWO_SPEECHES, 0)).toBeNull()
  })

  it('takes a new group above any in the scene', () => {
    const scene = [item('character', true, 3), item('dialogue', true, 3), item('character', true, 3), item('dialogue', true, 3), item('character'), item('dialogue'), item('character'), item('dialogue')]
    expect(planDualToggle(scene, 7)!.changes[0].dual_group).toBe(4)
    // The speech before is already in a pair, so it can't take a second partner.
    expect(dualAction(scene, 5)).toBeNull()
  })

  it('spans the shorter side so the next block starts below both', () => {
    const paired = TWO_SPEECHES.map((entry, index) => index >= 1 && index <= 5 ? item(entry.element_type, true, 1) : entry)
    const layout = dualLayout(paired)
    expect([...layout.entries()]).toEqual([
      [1, { side: 'left', span: 1 }], [2, { side: 'left', span: 2 }],
      [3, { side: 'right', span: 1 }], [4, { side: 'right', span: 1 }], [5, { side: 'right', span: 1 }],
    ])
  })
})
