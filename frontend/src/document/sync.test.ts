import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Editor } from '@tiptap/core'
import { TextSelection } from '@tiptap/pm/state'
import { type AgentProposal, ApiError, type Scene, type SceneContentResult } from '../api'
import { REMOTE, ScriptBehaviour } from './behaviour'
import { buildDoc, sceneNodes, type ServerBlock } from './convert'
import { buildDecorations, wordDiff } from './overlay'
import { schemaExtensions } from './schema'
import { DocumentSync, type SyncApi } from './sync'

const acts = [{ id: 1, screenplay_id: 1, title: 'Act One', position: 0 }]
const scene = (id: number, version: number, position = 0): Scene => ({ id, act_id: 1, heading: `INT. ROOM ${id} - DAY`, position, body: '', version, scene_instruction: '' })
const block = (id: number, text: string, element_type = 'action'): ServerBlock => ({ id, element_type, text, is_dual: false, dual_group: null, character_extension: null, origin: 'human', position: id })

type Workspace = { acts: typeof acts; scenes: Scene[]; blocks: Record<number, ServerBlock[]> }
const editors: Editor[] = []

function setup(workspace: Workspace, api: Partial<SyncApi> = {}) {
  const write = vi.fn<SyncApi['write']>()
  const refresh = vi.fn()
  const sync = new DocumentSync({ write, refresh, ...api })
  sync.init(workspace, [])
  const editor = new Editor({
    extensions: [...schemaExtensions(), ScriptBehaviour.configure({ owner: id => sync.owners.get(id) })],
    content: buildDoc(workspace),
    enableInputRules: false, enablePasteRules: false,
    onTransaction: ({ editor: current, transaction }) => { if (transaction.docChanged && !transaction.getMeta(REMOTE)) sync.noteChange(transaction.before, current.state.doc) },
  })
  editors.push(editor)
  sync.attach(editor)
  return { sync, editor, write, refresh }
}

function typeAtEnd(editor: Editor, text: string, current: string): void {
  let at = -1
  editor.state.doc.descendants((node, pos) => { if (at < 0 && node.type.name === 'element' && node.textContent === current) at = pos + 1 + node.content.size; return at < 0 })
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, at)))
  if (text) editor.commands.insertContent(text)
}

const texts = (editor: Editor, sceneId: number) => {
  const node = sceneNodes(editor.state.doc).get(sceneId)!.node
  const out: [number | null, string][] = []
  node.forEach(child => { if (child.type.name === 'element') out.push([child.attrs.block_id, child.textContent]) })
  return out
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); editors.splice(0).forEach(editor => editor.destroy()) })

describe('saving', () => {
  it('sends a dirty scene once, about a second after typing stops, and writes new ids back', async () => {
    const { sync, editor, write } = setup({ acts, scenes: [scene(7, 2), scene(8, 4, 1)], blocks: { 7: [block(20, 'One')], 8: [block(30, 'Other')] } })
    write.mockResolvedValue({ scene_id: 7, version: 3, block_ids: [20, 99], created_ids: [99] } satisfies SceneContentResult)
    typeAtEnd(editor, ' two', 'One')
    editor.commands.scriptEnter()
    editor.commands.insertContent('Three')
    await vi.advanceTimersByTimeAsync(900)
    expect(write).not.toHaveBeenCalled()
    expect(sync.getSnapshot().status).toBe('unsaved')
    await vi.advanceTimersByTimeAsync(200)
    expect(write).toHaveBeenCalledTimes(1)
    expect(write).toHaveBeenCalledWith(7, 2, { heading: 'INT. ROOM 7 - DAY', blocks: [
      { id: 20, element_type: 'action', text: 'One two', is_dual: false, dual_group: null, character_extension: null },
      { element_type: 'action', text: 'Three', is_dual: false, dual_group: null, character_extension: null },
    ] })
    await vi.runAllTimersAsync()
    expect(texts(editor, 7)).toEqual([[20, 'One two'], [99, 'Three']])
    expect(sync.versionOf(7)).toBe(3)
    expect(sync.getSnapshot().status).toBe('saved')
  })

  it('keeps editing safe while a save is in flight and saves the rest afterwards', async () => {
    let finish: (result: SceneContentResult) => void = () => undefined
    const { editor, write } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One')] } })
    write.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    write.mockResolvedValueOnce({ scene_id: 7, version: 4, block_ids: [20], created_ids: [] })
    typeAtEnd(editor, '!', 'One')
    await vi.advanceTimersByTimeAsync(1100)
    typeAtEnd(editor, '?', 'One!')
    finish({ scene_id: 7, version: 3, block_ids: [20], created_ids: [] })
    await vi.runAllTimersAsync()
    expect(write).toHaveBeenCalledTimes(2)
    expect(write.mock.calls[1][1]).toBe(3)
    expect(write.mock.calls[1][2].blocks[0].text).toBe('One!?')
  })

  it('turns a 409 into a Keep mine / Load theirs conflict, and Keep mine saves over the newer version', async () => {
    const { sync, editor, write, refresh } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One')] } })
    write.mockRejectedValueOnce(new ApiError(409, 'Version mismatch'))
    typeAtEnd(editor, ' mine', 'One')
    await vi.runAllTimersAsync()
    expect(sync.getSnapshot().conflicts.get(7)).toBe('stale')
    expect(refresh).toHaveBeenCalled()
    sync.reconcile({ acts, scenes: [scene(7, 5)], blocks: { 7: [block(20, 'Theirs')] } }, [])
    expect(texts(editor, 7)).toEqual([[20, 'One mine']])
    write.mockResolvedValueOnce({ scene_id: 7, version: 6, block_ids: [20], created_ids: [] })
    sync.keepMine(7)
    await vi.runAllTimersAsync()
    expect(write).toHaveBeenLastCalledWith(7, 5, expect.objectContaining({ blocks: [expect.objectContaining({ id: 20, text: 'One mine' })] }))
    expect(sync.getSnapshot().conflicts.size).toBe(0)
  })
})

describe('live sync', () => {
  it('replaces a clean scene in place and leaves the others alone', () => {
    const { editor, sync } = setup({ acts, scenes: [scene(7, 2), scene(8, 4, 1)], blocks: { 7: [block(20, 'One')], 8: [block(30, 'Other')] } })
    const untouched = sceneNodes(editor.state.doc).get(8)!.node
    sync.reconcile({ acts, scenes: [scene(7, 3), scene(8, 4, 1)], blocks: { 7: [block(20, 'One **more**'), block(21, 'New')], 8: [block(30, 'Other')] } }, [])
    expect(texts(editor, 7)).toEqual([[20, 'One more'], [21, 'New']])
    expect(sceneNodes(editor.state.doc).get(8)!.node).toBe(untouched)
    expect(sync.versionOf(7)).toBe(3)
    expect(editor.can().undo()).toBe(false)
  })

  it('flags a dirty scene instead of overwriting it, and Load theirs replaces it', () => {
    const { editor, sync } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One')] } })
    typeAtEnd(editor, ' mine', 'One')
    const theirs = { acts, scenes: [scene(7, 3)], blocks: { 7: [block(20, 'Theirs')] } }
    sync.reconcile(theirs, [])
    expect(sync.getSnapshot().conflicts.get(7)).toBe('remote')
    expect(texts(editor, 7)).toEqual([[20, 'One mine']])
    sync.loadTheirs(7)
    expect(texts(editor, 7)).toEqual([[20, 'Theirs']])
    expect(sync.isDirty(7)).toBe(false)
    expect(sync.getSnapshot().conflicts.size).toBe(0)
  })

  it('rebuilds around local scenes when a scene is added elsewhere', () => {
    const { editor, sync } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One')] } })
    typeAtEnd(editor, ' mine', 'One')
    sync.reconcile({ acts, scenes: [scene(7, 2), scene(9, 1, 1)], blocks: { 7: [block(20, 'One')], 9: [block(40, 'Added')] } }, [])
    expect([...sceneNodes(editor.state.doc).keys()]).toEqual([7, 9])
    expect(texts(editor, 7)).toEqual([[20, 'One mine']])
    expect(sync.isDirty(7)).toBe(true)
  })
})

describe('paste', () => {
  it('reads pasted plain text as Fountain lines', () => {
    const { editor } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, '')] } })
    typeAtEnd(editor, '', '')
    editor.view.pasteText('She waits.\nMIRA\nWe *should* go.')
    expect(texts(editor, 7)).toEqual([[20, 'She waits.'], [null, 'MIRA'], [null, 'We should go.']])
    const types: string[] = []
    sceneNodes(editor.state.doc).get(7)!.node.forEach(child => { if (child.type.name === 'element') types.push(String(child.attrs.element_type)) })
    expect(types).toEqual(['action', 'character', 'action'])
  })

  it('keeps the id of the element pasted into', () => {
    const { editor } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One'), block(21, 'Two')] } })
    typeAtEnd(editor, '', 'One')
    editor.view.pasteText(' more\nAnd more')
    expect(texts(editor, 7)).toEqual([[20, 'One more'], [null, 'And more'], [21, 'Two']])
  })
})

describe('overlay', () => {
  it('diffs words', () => {
    expect(wordDiff('Rain on the roses.', 'Rain hammers the roses.')).toEqual([
      { kind: 'same', text: 'Rain ' }, { kind: 'delete', text: 'on' }, { kind: 'insert', text: 'hammers' }, { kind: 'same', text: ' the roses.' },
    ])
  })

  it('names every element and shows a pending block proposal under its block', () => {
    const { editor } = setup({ acts, scenes: [scene(7, 2)], blocks: { 7: [block(20, 'One'), block(21, 'MIRA', 'character'), block(22, 'Two')] } })
    const proposal: AgentProposal = { id: 80, project_id: 1, run_id: null, target_kind: 'block', target_id: 22, operation: { text: 'Two, then three' }, diff: { summary: 'Extend' }, before: {}, base_version: 2, status: 'proposed' }
    const noop = () => undefined
    const set = buildDecorations(editor.state.doc, { proposals: [proposal], conflicts: new Map(), collapsed: new Set(), busy: new Set() }, { accept: noop, reject: noop, rollback: noop, keepMine: noop, loadTheirs: noop, toggleAct: noop })
    const decorations = set.find()
    const labels = decorations.map(item => (item as unknown as { type: { attrs?: Record<string, string> } }).type.attrs?.['aria-label']).filter(Boolean)
    expect(labels).toEqual(['Scene heading 1', 'Action 1', 'Character 1', 'Action 2'])
    const widgets = decorations.filter(item => (item as unknown as { type: { toDOM?: unknown } }).type.toDOM)
    expect(widgets).toHaveLength(1)
  })
})
