/** Smart typing: infer a screenplay element from what the writer typed, the way Final Draft does. */

const TRANSITION = /^[A-Z][A-Z .'-]*TO:$|^(FADE OUT\.|FADE TO BLACK\.|CUT TO BLACK\.)$/
const CHARACTER = /^[A-Z][A-Z0-9 .'-]{0,32}( \((V\.O\.|O\.S\.|O\.C\.|CONT'D|CONT’D)\))?$/
const PARENTHETICAL = /^\([^()]{1,60}\)$/

/**
 * Return the element a block should become, or ``null`` to leave it alone.
 *
 * Only an action block retypes itself, and only when the text is unambiguous: an all-caps short line
 * is a character cue, a line wrapped in parentheses is a parenthetical, and "… TO:" is a transition.
 */
export function inferElement(text: string, current: string): string | null {
  const line = text.trim()
  if (current !== 'action' || !line || line.includes('\n')) return null
  if (TRANSITION.test(line)) return 'transition'
  if (PARENTHETICAL.test(line)) return 'parenthetical'
  if (CHARACTER.test(line) && /[A-Z]{2}/.test(line) && !/[.!?]$/.test(line.replace(/\((V\.O\.|O\.S\.|O\.C\.)\)$/, ''))) return 'character'
  return null
}

/** Normalise text as it is typed into an element (character cues are always upper case). */
export function normalizeTyped(text: string, element: string): string {
  return element === 'character' ? text.toUpperCase() : text
}
