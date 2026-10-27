import { describe, expect, it } from 'vitest'
import { inferElement, normalizeTyped } from './smartTyping'

describe('smart typing', () => {
  it('turns an all-caps name into a character cue, with extensions', () => {
    expect(inferElement('EDWARD', 'action')).toBe('character')
    expect(inferElement('  YOUNG EDWARD (V.O.) ', 'action')).toBe('character')
    expect(inferElement("WILL (CONT'D)", 'action')).toBe('character')
  })

  it('recognises parentheticals and transitions', () => {
    expect(inferElement('(beat)', 'action')).toBe('parenthetical')
    expect(inferElement('CUT TO:', 'action')).toBe('transition')
    expect(inferElement('MATCH CUT TO:', 'action')).toBe('transition')
    expect(inferElement('FADE OUT.', 'action')).toBe('transition')
  })

  it('leaves ordinary action, shouted lines, other elements and multi-line text alone', () => {
    expect(inferElement('Edward wades into the river.', 'action')).toBeNull()
    expect(inferElement('BANG!', 'action')).toBeNull()
    expect(inferElement('A.', 'action')).toBeNull()
    expect(inferElement('EDWARD', 'dialogue')).toBeNull()
    expect(inferElement('EDWARD\nWILL', 'action')).toBeNull()
    expect(inferElement('', 'action')).toBeNull()
  })

  it('upper-cases character cues as they are typed', () => {
    expect(normalizeTyped('edward (v.o.)', 'character')).toBe('EDWARD (V.O.)')
    expect(normalizeTyped('Keep me.', 'action')).toBe('Keep me.')
  })
})
