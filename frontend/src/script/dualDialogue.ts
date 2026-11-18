/**
 * Dual dialogue, shared by the Classic and Document editors.
 *
 * A speech is a character cue and the parentheticals and dialogue under it. Two adjacent speeches
 * are paired when every block of both carries `is_dual` and the same `dual_group`; Fountain export
 * puts the `^` on the second cue. Drafts imported before groups existed mark only the second cue
 * (`is_dual`, no group), and that still reads as a pair.
 */

export type DualItem = { element_type: string; is_dual: boolean; dual_group: number | null }
/** A run of blocks, `start` inclusive and `end` exclusive. */
export type Speech = { start: number; end: number }
export type DualPair = { left: Speech; right: Speech }
export type DualChange = { index: number; is_dual: boolean; dual_group: number | null }

const SPEECH_TYPES = new Set(['character', 'parenthetical', 'dialogue'])

/** Split a scene's blocks into speeches. */
export function speeches(items: DualItem[]): Speech[] {
  const found: Speech[] = []
  let open: Speech | null = null
  items.forEach((item, index) => {
    if (!SPEECH_TYPES.has(item.element_type)) { open = null; return }
    if (item.element_type === 'character' || !open) { open = { start: index, end: index + 1 }; found.push(open) }
    else open.end = index + 1
  })
  return found
}

/** Return whether any block of a speech is dual, and its group. */
function dualOf(items: DualItem[], speech: Speech): { dual: boolean; group: number | null } {
  const dual = items.slice(speech.start, speech.end).filter(item => item.is_dual)
  return { dual: dual.length > 0, group: dual.find(item => item.dual_group !== null)?.dual_group ?? null }
}

/** Find the dual dialogue pairs in a scene's blocks. */
export function dualPairs(items: DualItem[]): DualPair[] {
  const all = speeches(items)
  const pairs: DualPair[] = []
  for (let index = 0; index + 1 < all.length; index += 1) {
    const left = all[index]
    const right = all[index + 1]
    if (left.end !== right.start) continue
    const a = dualOf(items, left)
    const b = dualOf(items, right)
    const grouped = a.dual && b.dual && (a.group === null || b.group === null || a.group === b.group)
    const legacy = !a.dual && b.dual && b.group === null
    if (grouped || legacy) { pairs.push({ left, right }); index += 1 }
  }
  return pairs
}

/** Return whether the block at `index` can be paired with the previous speech, unpaired, or neither. */
export function dualAction(items: DualItem[], index: number): 'pair' | 'unpair' | null {
  return planDualToggle(items, index)?.action ?? null
}

/**
 * Plan "pair with previous dialogue" for the block at `index`: unpair its pair when it is in one,
 * otherwise pair its speech with the speech just before it. Returns the blocks to change.
 */
export function planDualToggle(items: DualItem[], index: number): { action: 'pair' | 'unpair'; changes: DualChange[] } | null {
  const all = speeches(items)
  const at = all.findIndex(speech => index >= speech.start && index < speech.end)
  if (at < 0) return null
  const inSpeech = (speech: Speech) => Array.from({ length: speech.end - speech.start }, (_, offset) => speech.start + offset)
  const pairs = dualPairs(items)
  const pair = pairs.find(item => item.left.start === all[at].start || item.right.start === all[at].start)
  if (pair) {
    return { action: 'unpair', changes: [...inSpeech(pair.left), ...inSpeech(pair.right)].map(position => ({ index: position, is_dual: false, dual_group: null })) }
  }
  const previous = all[at - 1]
  if (!previous || previous.end !== all[at].start) return null
  if (pairs.some(item => item.left.start === previous.start || item.right.start === previous.start)) return null
  const group = Math.max(0, ...items.map(item => item.dual_group ?? 0)) + 1
  return { action: 'pair', changes: [...inSpeech(previous), ...inSpeech(all[at])].map(position => ({ index: position, is_dual: true, dual_group: group })) }
}

/**
 * Lay out the pairs side by side: the column of each block in a pair, and how many grid rows the
 * shorter side's last block spans so the next block starts below both.
 */
export function dualLayout(items: DualItem[]): Map<number, { side: 'left' | 'right'; span: number }> {
  const layout = new Map<number, { side: 'left' | 'right'; span: number }>()
  for (const { left, right } of dualPairs(items)) {
    const leftRows = left.end - left.start
    const rightRows = right.end - right.start
    for (let index = left.start; index < left.end; index += 1) layout.set(index, { side: 'left', span: index === left.end - 1 ? Math.max(1, rightRows - leftRows + 1) : 1 })
    for (let index = right.start; index < right.end; index += 1) layout.set(index, { side: 'right', span: index === right.end - 1 ? Math.max(1, leftRows - rightRows + 1) : 1 })
  }
  return layout
}
