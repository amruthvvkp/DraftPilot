import { afterEach, describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/core'
import { TextSelection } from '@tiptap/pm/state'
import type { Scene } from '../api'
import type { Beat } from '../storyApi'
import { ScriptBehaviour } from './behaviour'
import { buildDoc, layoutAct, sceneNodes, serializeScene, type ServerBlock } from './convert'
import { parseInline, serializeInline } from './fountain'
import { schemaExtensions } from './schema'
import { planEnter, planTab } from './typingRules'

const block = (id: number, element_type: string, text: string, extra: Partial<ServerBlock> = {}): ServerBlock =>
  ({ id, element_type, text, is_dual: false, dual_group: null, character_extension: null, origin: 'human', position: id, ...extra })

const scene = (id: number, heading: string, version = 1, act_id = 1, position = 0): Scene =>
  ({ id, act_id, heading, position, body: '', version, scene_instruction: '' })

const EVERY_TYPE: ServerBlock[] = [
  block(1, 'action', 'The house breathes in the **dark**.'),
  block(2, 'character', 'MIRA', { character_extension: 'V.O.' }),
  block(3, 'parenthetical', '(quietly)'),
  block(4, 'dialogue', 'We *should* go.', { is_dual: true, dual_group: 7 }),
  block(5, 'character', 'EDWARD', { is_dual: true, dual_group: 7 }),
  block(6, 'dialogue', 'Not _yet_.', { is_dual: true, dual_group: 7 }),
  block(7, 'transition', 'CUT TO:'),
  block(8, 'lyric', '~~Hush~~ little house'),
  block(9, 'note', 'Check the [[color:#dda05d]]lantern[[/color]] prop.'),
  block(10, 'section', 'Act one'),
  block(11, 'synopsis', 'They arrive.'),
  block(12, 'shot', 'CLOSE ON the lantern'),
  block(13, 'page_break', ''),
  block(14, 'action', 'Line one\nLine two with ***both***.'),
]

const editors: Editor[] = []
afterEach(() => { editors.splice(0).forEach(editor => editor.destroy()) })

/** Build an editor over one or two scenes, with block ownership as the server would report it. */
function makeEditor(blocks: Record<number, ServerBlock[]>, scenes: Scene[] = [scene(7, 'INT. LANTERN HOUSE - NIGHT')]): Editor {
  const owners = new Map<number, number>()
  for (const [sceneId, list] of Object.entries(blocks)) list.forEach(item => owners.set(item.id, Number(sceneId)))
  const editor = new Editor({
    extensions: [...schemaExtensions(), ScriptBehaviour.configure({ owner: id => owners.get(id) })],
    content: buildDoc({ acts: [{ id: 1, screenplay_id: 1, title: 'Act One', position: 0 }], scenes, blocks }),
    enableInputRules: false, enablePasteRules: false,
  })
  editors.push(editor)
  return editor
}

function sceneOf(editor: Editor, sceneId = 7) {
  return serializeScene(sceneNodes(editor.state.doc).get(sceneId)!.node, () => true)
}

/** Put the cursor inside the element holding `text`, at `offset` (or its end). */
function cursorIn(editor: Editor, text: string, offset?: number): void {
  let target = -1
  editor.state.doc.descendants((node, pos) => {
    if (target < 0 && node.isTextblock && node.textContent === text) target = pos + 1 + (offset ?? node.content.size)
    return target < 0
  })
  expect(target).toBeGreaterThan(0)
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, target)))
}

/** Press a key the way a browser would, through the editor's keymaps (selection included). */
function press(editor: Editor, shortcut: string): void {
  const parts = shortcut.split('-')
  const key = parts.pop()!
  const mod = parts.includes('Mod')
  const mac = /Mac|iP(hone|[oa]d)/.test(navigator.platform)
  const event = new KeyboardEvent('keydown', {
    key, bubbles: true, cancelable: true, shiftKey: parts.includes('Shift'), altKey: parts.includes('Alt'),
    metaKey: mod && mac, ctrlKey: mod && !mac,
  })
  editor.view.someProp('handleKeyDown', handler => handler(editor.view, event))
}

const types = (editor: Editor, sceneId = 7) => sceneOf(editor, sceneId).content.blocks.map(item => item.element_type)

describe('Fountain inline markup', () => {
  it.each([
    'plain', '**bold**', '*italic*', '_under_', '~~gone~~', '***both***', 'a **b** *c* _d_',
    '[[color:#dda05d]]amber[[/color]]', 'snake_case_name', '2 * 3 = 6', 'a ** b', '[[color:#dda05d]]**x**[[/color]]', '',
  ])('round-trips %j', text => {
    expect(serializeInline(parseInline(text))).toBe(text)
  })

  it('reads marks', () => {
    expect(parseInline('a **b** *c*')).toEqual([
      { text: 'a ', marks: [] }, { text: 'b', marks: [{ type: 'bold' }] }, { text: ' ', marks: [] }, { text: 'c', marks: [{ type: 'italic' }] },
    ])
    expect(parseInline('\\*not italic\\*')).toEqual([{ text: '*not italic*', marks: [] }])
  })

  it('escapes literal markup only when it would read as a mark', () => {
    expect(serializeInline([{ text: '*not italic*', marks: [] }])).toBe('\\*not italic\\*')
    expect(serializeInline([{ text: '2 * 3', marks: [] }])).toBe('2 * 3')
  })
})

describe('document round trip', () => {
  it('serialises every element type, mark and dual dialogue back to the same blocks', () => {
    const editor = makeEditor({ 7: EVERY_TYPE })
    const { content, newUids } = sceneOf(editor)
    expect(newUids).toEqual([])
    expect(content.heading).toBe('INT. LANTERN HOUSE - NIGHT')
    expect(content.blocks).toEqual(EVERY_TYPE.map(({ id, element_type, text, is_dual, dual_group, character_extension }) => ({ id, element_type, text, is_dual, dual_group, character_extension })))
  })

  it('serialises edited marks to Fountain', () => {
    const editor = makeEditor({ 7: [block(1, 'action', 'The house breathes.')] })
    cursorIn(editor, 'The house breathes.', 0)
    editor.commands.setTextSelection({ from: editor.state.selection.from + 4, to: editor.state.selection.from + 9 })
    editor.commands.toggleBold()
    expect(sceneOf(editor).content.blocks[0].text).toBe('The **house** breathes.')
    editor.commands.toggleMark('color', { color: '#dda05d' })
    expect(sceneOf(editor).content.blocks[0].text).toBe('The [[color:#dda05d]]**house**[[/color]] breathes.')
  })

  it('upper-cases a typed character cue', () => {
    const editor = makeEditor({ 7: [block(1, 'character', 'MIRA')] })
    cursorIn(editor, 'MIRA')
    editor.commands.insertContent(' jr')
    expect(sceneOf(editor).content.blocks[0].text).toBe('MIRA JR')
  })
})

describe('block ids', () => {
  it('keep the id on the first half of a split', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One two')] })
    cursorIn(editor, 'One two', 3)
    editor.commands.scriptEnter()
    const { content, newUids } = sceneOf(editor)
    expect(content.blocks.map(item => [item.id, item.text])).toEqual([[20, 'One'], [undefined, ' two']])
    expect(newUids).toHaveLength(1)
  })

  it('keep the id with the text when Enter opens a line above', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One')] })
    cursorIn(editor, 'One', 0)
    editor.commands.scriptEnter()
    expect(sceneOf(editor).content.blocks.map(item => [item.id, item.text])).toEqual([[undefined, ''], [20, 'One']])
  })

  it('keep the first id on a merge and drop the second block', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One'), block(21, 'action', 'Two')] })
    cursorIn(editor, 'Two', 0)
    editor.commands.joinBackward()
    expect(sceneOf(editor).content.blocks.map(item => [item.id, item.text])).toEqual([[20, 'OneTwo']])
  })

  it('come back on undo, and redo splits again', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One two')] })
    cursorIn(editor, 'One two', 3)
    editor.commands.scriptEnter()
    editor.commands.undo()
    expect(sceneOf(editor).content.blocks.map(item => [item.id, item.text])).toEqual([[20, 'One two']])
    editor.commands.redo()
    expect(sceneOf(editor).content.blocks.map(item => item.id)).toEqual([20, undefined])
  })

  it('are not duplicated by a paste of an existing block', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One'), block(21, 'action', 'Two')] })
    const copy = editor.state.doc.nodeAt(sceneNodes(editor.state.doc).get(7)!.pos + 1 + editor.state.doc.nodeAt(sceneNodes(editor.state.doc).get(7)!.pos)!.child(0).nodeSize)!
    cursorIn(editor, 'Two')
    editor.commands.insertContentAt(editor.state.selection.to + 1, copy.toJSON())
    const ids = sceneOf(editor).content.blocks.map(item => item.id)
    expect(ids).toEqual([20, 21, undefined])
  })

  it('are not carried into another scene', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One')], 8: [block(30, 'action', 'Elsewhere')] }, [scene(7, 'INT. A - DAY'), scene(8, 'INT. B - DAY', 1, 1, 1)])
    const moved = sceneNodes(editor.state.doc).get(7)!.node.child(1)
    cursorIn(editor, 'Elsewhere')
    editor.commands.insertContentAt(editor.state.selection.to + 1, moved.toJSON())
    expect(sceneOf(editor, 8).content.blocks.map(item => item.id)).toEqual([30, undefined])
  })

  it('refuse edits that would delete a scene', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'One')], 8: [block(30, 'action', 'Two')] }, [scene(7, 'INT. A - DAY'), scene(8, 'INT. B - DAY', 1, 1, 1)])
    editor.commands.setTextSelection({ from: 1, to: editor.state.doc.content.size - 1 })
    editor.commands.deleteSelection()
    expect([...sceneNodes(editor.state.doc).keys()]).toEqual([7, 8])
  })
})

describe('typing rules', () => {
  it.each([
    ['action', 'action'], ['character', 'dialogue'], ['dialogue', 'action'], ['parenthetical', 'dialogue'], ['transition', 'action'],
  ])('Enter in %s gives %s', (from, next) => {
    expect(planEnter(from, 'x', null)).toEqual({ split: true, next })
  })

  it('Enter on the empty action after dialogue gives a character cue', () => {
    expect(planEnter('action', '', 'dialogue')).toEqual({ retype: 'character', split: false, next: 'character' })
  })

  it.each([['action', 'character'], ['dialogue', 'parenthetical'], ['character', 'transition']])('Tab in %s gives %s', (from, next) => {
    expect(planTab(from, false)).toBe(next)
  })

  it('writes a scene from the keyboard: Enter and Tab walk the elements', () => {
    const editor = makeEditor({ 7: [block(20, 'action', '')] })
    cursorIn(editor, '')
    editor.commands.insertContent('The door opens.')
    press(editor, 'Enter')
    press(editor, 'Tab')
    editor.commands.insertContent('mira')
    press(editor, 'Enter')
    editor.commands.insertContent('Hello?')
    press(editor, 'Enter')
    press(editor, 'Enter')
    editor.commands.insertContent('EDWARD')
    press(editor, 'Enter')
    press(editor, 'Tab')
    editor.commands.insertContent('(softly)')
    press(editor, 'Enter')
    editor.commands.insertContent('Here.')
    expect(sceneOf(editor).content.blocks.map(item => [item.element_type, item.text])).toEqual([
      ['action', 'The door opens.'], ['character', 'MIRA'], ['dialogue', 'Hello?'], ['character', 'EDWARD'], ['parenthetical', '(softly)'], ['dialogue', 'Here.'],
    ])
  })

  it('smart typing retypes an unambiguous action line on Enter', () => {
    const editor = makeEditor({ 7: [block(20, 'action', '')] })
    cursorIn(editor, '')
    editor.commands.insertContent('EDWARD')
    press(editor, 'Enter')
    expect(types(editor)).toEqual(['character', 'dialogue'])
  })

  it('Mod-number sets the element type', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'Hello')] })
    cursorIn(editor, 'Hello')
    press(editor, 'Mod-5')
    expect(types(editor)).toEqual(['dialogue'])
    press(editor, 'Mod-Alt-6')
    expect(types(editor)).toEqual(['transition'])
  })

  it('Enter in a scene heading moves into the scene', () => {
    const editor = makeEditor({ 7: [block(20, 'action', 'Already here')] })
    cursorIn(editor, 'INT. LANTERN HOUSE - NIGHT')
    press(editor, 'Enter')
    editor.commands.insertContent('First.')
    expect(sceneOf(editor).content.blocks.map(item => item.text)).toEqual(['First.', 'Already here'])
  })

  it('pairs a dialogue with the previous one', () => {
    const editor = makeEditor({ 7: [block(1, 'character', 'A'), block(2, 'dialogue', 'One'), block(3, 'character', 'B'), block(4, 'dialogue', 'Two')] })
    cursorIn(editor, 'Two')
    editor.commands.toggleDualDialogue()
    const blocks = sceneOf(editor).content.blocks
    expect(blocks[1].is_dual && blocks[3].is_dual && blocks[1].dual_group === blocks[3].dual_group).toBe(true)
  })
})

describe('outline layout', () => {
  it('keeps an unlinked beat in its own act, even one with no scenes yet', () => {
    const ledger = { id: 9, project_id: 1, version: 1, act_id: 2, position: 0, title: 'The ledger', summary: '', beat_type: 'beat', status: 'draft', scene_ids: [], character_ids: [], source: 'writer' as const }
    const doc = buildDoc({ acts: [{ id: 1, screenplay_id: 1, title: 'Act One', position: 0 }, { id: 2, screenplay_id: 1, title: 'Act Two', position: 1 }], scenes: [scene(7, 'A')], blocks: {} }, [ledger])
    expect(doc.content![1].content!.map(item => item.attrs?.beat_id)).toEqual([9])
  })

  const beat = (id: number, position: number, scene_ids: number[]): Beat =>
    ({ id, project_id: 1, version: 1, act_id: 1, position, title: `Beat ${id}`, summary: '', beat_type: 'beat', status: 'draft', scene_ids, character_ids: [], source: 'writer' })

  it('puts a linked beat above its first scene and an unlinked one after the previous beat', () => {
    const items = layoutAct([scene(7, 'A', 1, 1, 0), scene(8, 'B', 1, 1, 1)], [beat(1, 0, [7]), beat(2, 1, []), beat(3, 2, [8]), beat(0, -1, [])])
    expect(items.map(item => item.kind === 'beat' ? `b${item.beat.id}` : `s${item.scene.id}`)).toEqual(['b0', 'b1', 's7', 'b2', 'b3', 's8'])
  })
})
