/** Final Draft's typing habits as data: what Enter, Tab and ⌘1–9 give in each element. */
import { inferElement } from '../smartTyping'

/** Enter ends an element and starts the next one of this type. */
export const ENTER_NEXT: Record<string, string> = {
  action: 'action', character: 'dialogue', dialogue: 'action', parenthetical: 'dialogue', transition: 'action',
}

/** Tab retypes the current element. */
export const TAB_NEXT: Record<string, string> = {
  action: 'character', dialogue: 'parenthetical', character: 'transition', parenthetical: 'dialogue', transition: 'action',
}

/** Shift+Tab steps back through the same cycle. */
export const SHIFT_TAB_NEXT: Record<string, string> = {
  character: 'action', parenthetical: 'dialogue', transition: 'character', dialogue: 'character',
}

/** ⌘1–⌘9 (or ⌘⌥1–9 where the browser keeps ⌘1–9 for tabs): Final Draft's numbering from ⌘2 on. */
export const SHORTCUT_TYPES = ['section', 'action', 'character', 'parenthetical', 'dialogue', 'transition', 'shot', 'lyric', 'note']

export type EnterPlan = { retype?: string; split: boolean; next: string }

/**
 * Decide what Enter does in an element of `type` holding `text`, after an element of `previous`.
 *
 * Smart typing retypes an unambiguous action line first (`EDWARD` becomes a character cue), and Enter
 * on the empty action that follows dialogue turns it into a character cue ("twice: character").
 */
export function planEnter(type: string, text: string, previous: string | null): EnterPlan {
  if (!text.trim() && type === 'action' && previous === 'dialogue') return { retype: 'character', split: false, next: 'character' }
  const inferred = inferElement(text, type) ?? type
  return { ...(inferred !== type ? { retype: inferred } : {}), split: true, next: ENTER_NEXT[inferred] ?? 'action' }
}

/** Return the type Tab (or Shift+Tab) gives an element, or null to leave it. */
export function planTab(type: string, shift: boolean): string | null {
  return (shift ? SHIFT_TAB_NEXT : TAB_NEXT)[type] ?? null
}
