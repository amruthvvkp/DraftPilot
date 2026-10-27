/**
 * The editor's behaviour: typing rules, block identity, structure guard and paste handling.
 *
 * Transactions tagged with the `remote` meta come from the server (loads, live sync, saved ids) and
 * skip the guard and dirty tracking.
 */
import { Extension } from '@tiptap/core'
import { Fragment, type Node as PMNode, type NodeType, Slice } from '@tiptap/pm/model'
import { type EditorState, Plugin, PluginKey, TextSelection, type Transaction } from '@tiptap/pm/state'
import { inferElement } from '../smartTyping'
import { inlineContent, structureKey } from './convert'
import { newUid } from './schema'
import { planEnter, planTab, SHORTCUT_TYPES } from './typingRules'

export const REMOTE = 'draftpilot:remote'
type Dispatch = ((tr: Transaction) => void) | undefined

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    script: {
      /** Set the element type of every element in the selection. */
      setElementType: (type: string) => ReturnType
      /** Enter, by the typing rules. */
      scriptEnter: () => ReturnType
      /** Tab or Shift+Tab, by the typing rules. */
      scriptTab: (shift?: boolean) => ReturnType
      /** Toggle "pair with previous dialogue" on the dialogue under the cursor. */
      toggleDualDialogue: () => ReturnType
    }
  }
}

export type BehaviourOptions = {
  /** The scene that owns a block id, as the server last said. */
  owner: (blockId: number) => number | undefined
}

/** Return the element under the cursor and its position, if the cursor is in one. */
export function currentElement(state: EditorState): { node: PMNode; pos: number; scene: PMNode; scenePos: number; index: number } | null {
  const { $from } = state.selection
  if ($from.parent.type.name !== 'element') return null
  return { node: $from.parent, pos: $from.before(), scene: $from.node($from.depth - 1), scenePos: $from.before($from.depth - 1), index: $from.index($from.depth - 1) }
}

/** Put the cursor in the scene's first element, creating an action when the scene has none. */
function enterScene(tr: Transaction, headingEnd: number, scene: PMNode, element: NodeType): void {
  const first = scene.childCount > 1 ? scene.child(1) : null
  if (!first || first.content.size > 0) tr.insert(headingEnd, element.create({ uid: newUid(), element_type: 'action' }))
  tr.setSelection(TextSelection.create(tr.doc, headingEnd + 1))
}

/** Enter by the typing rules table. */
export function scriptEnter(state: EditorState, dispatch: Dispatch): boolean {
  const element = state.schema.nodes.element
  const tr = state.tr
  if (!state.selection.empty) tr.deleteSelection()
  const $pos = tr.selection.$from
  if ($pos.parent.type.name === 'sceneHeading') {
    if (dispatch) { enterScene(tr, $pos.after(), $pos.node($pos.depth - 1), element); dispatch(tr.scrollIntoView()) }
    return true
  }
  if ($pos.parent.type !== element) return false
  const node = $pos.parent
  const scene = $pos.node($pos.depth - 1)
  const index = $pos.index($pos.depth - 1)
  const previous = index > 1 ? String(scene.child(index - 1).attrs.element_type) : null
  const plan = planEnter(String(node.attrs.element_type), node.textContent, previous)
  if (!dispatch) return true
  const nodePos = $pos.before()
  if (plan.retype) tr.setNodeMarkup(nodePos, undefined, { ...node.attrs, element_type: plan.retype })
  if (plan.split) {
    if ($pos.parentOffset === 0 && node.content.size > 0) {
      // At the start of a line, open a blank one above so the block (and its id) stays with its text.
      tr.insert(nodePos, element.create({ uid: newUid(), element_type: 'action' }))
    } else {
      tr.split($pos.pos, 1, [{ type: element, attrs: { uid: newUid(), element_type: plan.next } }])
    }
  }
  dispatch(tr.scrollIntoView())
  return true
}

/** Tab or Shift+Tab: retype the element; in a heading, Tab moves into the scene. */
export function scriptTab(shift: boolean) {
  return (state: EditorState, dispatch: Dispatch): boolean => {
    const { $from } = state.selection
    if ($from.parent.type.name === 'sceneHeading') {
      if (shift) return false
      if (dispatch) { const tr = state.tr; enterScene(tr, $from.after(), $from.node($from.depth - 1), state.schema.nodes.element); dispatch(tr.scrollIntoView()) }
      return true
    }
    const current = currentElement(state)
    if (!current) return false
    const next = planTab(String(current.node.attrs.element_type), shift)
    if (next && dispatch) dispatch(state.tr.setNodeMarkup(current.pos, undefined, { ...current.node.attrs, element_type: next }))
    return true
  }
}

/** Set the type of every element the selection touches. */
export function setElementType(type: string) {
  return (state: EditorState, dispatch: Dispatch): boolean => {
    const { from, to } = state.selection
    const tr = state.tr
    state.doc.nodesBetween(from, to, (node, pos) => {
      if (node.type.name === 'element') { if (node.attrs.element_type !== type) tr.setNodeMarkup(pos, undefined, { ...node.attrs, element_type: type }); return false }
      return true
    })
    if (!tr.docChanged) return false
    if (dispatch) dispatch(tr)
    return true
  }
}

/** Pair a dialogue element with the previous dialogue (dual dialogue), or unpair it. */
export function toggleDualDialogue(state: EditorState, dispatch: Dispatch): boolean {
  const current = currentElement(state)
  if (!current || current.node.attrs.element_type !== 'dialogue') return false
  if (!dispatch) return true
  const tr = state.tr
  if (current.node.attrs.is_dual) {
    tr.setNodeMarkup(current.pos, undefined, { ...current.node.attrs, is_dual: false, dual_group: null })
  } else {
    // The pair shares a dual_group: the previous dialogue's, or a new one.
    let group: number | null = null
    let previousPos = -1
    let pos = current.scenePos + 1
    for (let index = 0; index < current.index; index += 1) {
      const child = current.scene.child(index)
      if (child.attrs.element_type === 'dialogue') { group = (child.attrs.dual_group as number | null) ?? null; previousPos = pos }
      pos += child.nodeSize
    }
    if (previousPos < 0) return false
    const previous = tr.doc.nodeAt(previousPos)!
    const groupId = group ?? Date.now() % 1_000_000
    tr.setNodeMarkup(previousPos, undefined, { ...previous.attrs, is_dual: true, dual_group: groupId })
    tr.setNodeMarkup(current.pos, undefined, { ...current.node.attrs, is_dual: true, dual_group: groupId })
  }
  dispatch(tr)
  return true
}

/**
 * Keep block identity sound after any edit: every element gets a unique `uid`, and a `block_id` is
 * cleared when another element already holds it (a split, a paste) or when its scene doesn't own it
 * (moved from another scene, or restored by undo after the server deleted it). Cleared elements are
 * saved as new blocks.
 */
function identityPlugin(owner: (blockId: number) => number | undefined): Plugin {
  return new Plugin({
    key: new PluginKey('scriptIdentity'),
    appendTransaction(transactions, _old, state) {
      if (!transactions.some(tr => tr.docChanged)) return null
      const tr = state.tr
      const uids = new Set<string>()
      const seenBlocks = new Set<number>()
      state.doc.descendants((node, pos, parent) => {
        if (node.type.name !== 'element') return node.type.name !== 'beatNote' && node.type.name !== 'sceneHeading'
        const sceneId = Number(parent?.attrs.scene_id)
        let { uid, block_id: blockId } = node.attrs as { uid: string | null; block_id: number | null }
        let changed = false
        if (!uid || uids.has(uid)) { uid = newUid(); changed = true }
        uids.add(uid)
        if (blockId !== null && (owner(blockId) !== sceneId || seenBlocks.has(blockId))) { blockId = null; changed = true }
        if (blockId !== null) seenBlocks.add(blockId)
        if (changed) tr.setNodeMarkup(pos, undefined, { ...node.attrs, uid, block_id: blockId, source: blockId === null ? null : node.attrs.source })
        return false
      })
      if (!tr.docChanged) return null
      return tr.setMeta('addToHistory', false).setMeta('scriptIdentity', true)
    },
  })
}

/** Refuse local edits that would add, remove or reorder acts, beats or scenes (those go through the navigator). */
function structureGuard(): Plugin {
  return new Plugin({
    key: new PluginKey('scriptStructure'),
    filterTransaction(tr, state) {
      if (!tr.docChanged || tr.getMeta(REMOTE)) return true
      return structureKey(tr.doc) === structureKey(state.doc)
    },
  })
}

/** Flatten pasted scenes and acts into elements, and read pasted plain text as Fountain lines. */
function pastePlugin(): Plugin {
  return new Plugin({
    key: new PluginKey('scriptPaste'),
    props: {
      transformPasted(slice, view) {
        let structural = false
        slice.content.descendants(node => { if (['act', 'scene', 'beatNote', 'sceneHeading'].includes(node.type.name)) structural = true; return !structural })
        if (!structural) return slice
        const { element } = view.state.schema.nodes
        const elements: PMNode[] = []
        slice.content.descendants(node => {
          if (node.type.name === 'element') { elements.push(node); return false }
          if (node.type.name === 'sceneHeading') { elements.push(element.create({ uid: newUid(), element_type: 'action' }, node.content)); return false }
          return node.type.name !== 'beatNote'
        })
        return new Slice(Fragment.fromArray(elements), 0, 0)
      },
      clipboardTextParser(text, context, _plain, view) {
        const { schema } = view.state
        const lines = text.replace(/\r\n?/g, '\n').split('\n')
        // The first line joins the element under the cursor; it carries that element's identity, so
        // the block keeps its id even when ProseMirror replaces an empty element outright.
        const target = context.parent.type.name === 'element' ? context.parent : null
        const nodes = lines.map((line, index) => {
          const inferred = inferElement(line, 'action') ?? 'action'
          const attrs = index === 0 && target
            ? { ...target.attrs, element_type: target.content.size === 0 && target.attrs.element_type === 'action' ? inferred : target.attrs.element_type }
            : { uid: newUid(), element_type: inferred }
          return schema.nodes.element.create(attrs, inlineContent(line).map(item => schema.nodeFromJSON(item)))
        })
        return new Slice(Fragment.fromArray(nodes), 1, 1)
      },
    },
  })
}

/** Typing rules, element shortcuts, identity, the structure guard and paste handling. */
export const ScriptBehaviour = Extension.create<BehaviourOptions>({
  name: 'scriptBehaviour',
  priority: 1000,
  addOptions() { return { owner: () => undefined } },
  addCommands() {
    return {
      setElementType: (type: string) => ({ state, dispatch }) => setElementType(type)(state, dispatch),
      scriptEnter: () => ({ state, dispatch }) => scriptEnter(state, dispatch),
      scriptTab: (shift = false) => ({ state, dispatch }) => scriptTab(shift)(state, dispatch),
      toggleDualDialogue: () => ({ state, dispatch }) => toggleDualDialogue(state, dispatch),
    }
  },
  addKeyboardShortcuts() {
    const shortcuts: Record<string, () => boolean> = {
      Enter: () => this.editor.commands.scriptEnter(),
      'Shift-Enter': () => this.editor.commands.insertContent('\n'),
      Tab: () => this.editor.commands.scriptTab(false),
      'Shift-Tab': () => this.editor.commands.scriptTab(true),
    }
    SHORTCUT_TYPES.forEach((type, index) => {
      shortcuts[`Mod-${index + 1}`] = () => this.editor.commands.setElementType(type)
      shortcuts[`Mod-Alt-${index + 1}`] = () => this.editor.commands.setElementType(type)
    })
    return shortcuts
  },
  addProseMirrorPlugins() {
    return [identityPlugin(this.options.owner), structureGuard(), pastePlugin()]
  },
})
