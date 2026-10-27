/**
 * The document editor's schema: one ProseMirror document per draft.
 *
 *   doc → act → (beatNote | scene) → sceneHeading + element*
 *
 * Every `element` is one screenplay block and carries its `block_id`; `uid` is a client-only identity
 * that lets the editor find a node again after a save or a remote reload.
 */
import { Extension, Mark, Node, mergeAttributes } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Text from '@tiptap/extension-text'
import Bold from '@tiptap/extension-bold'
import Italic from '@tiptap/extension-italic'
import Underline from '@tiptap/extension-underline'
import Strike from '@tiptap/extension-strike'
import { UndoRedo } from '@tiptap/extensions'
import { AMBER } from './fountain'

export const ELEMENT_LABELS: Record<string, string> = {
  action: 'Action', character: 'Character', dialogue: 'Dialogue', parenthetical: 'Parenthetical', transition: 'Transition',
  lyric: 'Lyric', note: 'Note', section: 'Section', synopsis: 'Synopsis', shot: 'Shot', page_break: 'Page break',
}

let uidCounter = 0
/** Return a fresh client-side node identity. */
export function newUid(): string {
  uidCounter += 1
  return `u${Date.now().toString(36)}${uidCounter.toString(36)}`
}

const numberAttr = (name: string) => ({
  default: null,
  parseHTML: (element: HTMLElement) => { const value = element.getAttribute(name); return value && /^\d+$/.test(value) ? Number(value) : null },
  renderHTML: () => ({}),
})

export const ScriptDoc = Document.extend({ content: 'act+' })

export const Act = Node.create({
  name: 'act',
  content: '(beatNote | scene)*',
  isolating: true,
  defining: true,
  addAttributes() {
    return { act_id: numberAttr('data-act-id'), title: { default: '', rendered: false } }
  },
  parseHTML() { return [{ tag: 'section[data-act-id]' }] },
  renderHTML({ node, HTMLAttributes }) {
    return ['section', mergeAttributes(HTMLAttributes, { class: 'script-act', 'data-act-id': node.attrs.act_id }),
      ['header', { class: 'act-heading outline-only', contenteditable: 'false' },
        ['button', { type: 'button', class: 'act-toggle', tabindex: '-1', 'aria-label': `Collapse or expand ${node.attrs.title || 'act'}` }, '▾'],
        ['span', { class: 'act-title' }, node.attrs.title || 'Act']],
      ['div', { class: 'act-body' }, 0]]
  },
})

export const BeatNote = Node.create({
  name: 'beatNote',
  atom: true,
  selectable: false,
  draggable: false,
  addAttributes() {
    return {
      beat_id: numberAttr('data-beat-id'),
      version: { default: 0, rendered: false },
      title: { default: '', rendered: false },
      summary: { default: '', rendered: false },
      act_id: { default: null, rendered: false },
      linked: { default: false, rendered: false },
    }
  },
  parseHTML() { return [{ tag: 'aside[data-beat-id]' }] },
  renderHTML({ node }) {
    return ['aside', { class: 'beat-note outline-only', 'data-beat-id': node.attrs.beat_id, contenteditable: 'false' }, node.attrs.title]
  },
})

export const Scene = Node.create({
  name: 'scene',
  content: 'sceneHeading element*',
  isolating: true,
  defining: true,
  addAttributes() {
    return { scene_id: numberAttr('data-scene-id'), version: { default: 0, rendered: false } }
  },
  parseHTML() { return [{ tag: 'section[data-scene-id]' }] },
  renderHTML({ node, HTMLAttributes }) {
    return ['section', mergeAttributes(HTMLAttributes, { class: 'script-scene', 'data-scene-id': node.attrs.scene_id }), 0]
  },
})

export const SceneHeading = Node.create({
  name: 'sceneHeading',
  content: 'text*',
  marks: '',
  defining: true,
  parseHTML() { return [{ tag: 'h3.scene-heading' }] },
  renderHTML() { return ['h3', { class: 'scene-heading' }, 0] },
})

export const Element = Node.create({
  name: 'element',
  content: 'text*',
  marks: '_',
  defining: true,
  addAttributes() {
    return {
      uid: { default: null, keepOnSplit: false, rendered: false },
      block_id: { ...numberAttr('data-block-id'), keepOnSplit: false },
      element_type: { default: 'action', parseHTML: (element: HTMLElement) => element.getAttribute('data-type') ?? 'action', renderHTML: () => ({}) },
      origin: { default: 'human', keepOnSplit: false, rendered: false },
      is_dual: { default: false, rendered: false },
      dual_group: { default: null, rendered: false },
      character_extension: { default: null, keepOnSplit: false, rendered: false },
      // The block's text as the server last sent it; reused verbatim when the marks still match it.
      source: { default: null, keepOnSplit: false, rendered: false },
    }
  },
  parseHTML() { return [{ tag: 'p[data-type]' }] },
  renderHTML({ node }) {
    return ['p', elementAttributes(node.attrs), 0]
  },
  // Patch the paragraph in place when only attributes change (a save writing back a block id, a
  // retype), instead of rebuilding its DOM under the writer's cursor and selection.
  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement('p')
      let current = node
      const apply = (attrs: Record<string, unknown>) => {
        const wanted = elementAttributes(attrs)
        for (const name of ['class', 'data-type', 'data-block-id']) {
          const value = wanted[name as keyof typeof wanted]
          if (value === undefined) dom.removeAttribute(name)
          else if (dom.getAttribute(name) !== String(value)) dom.setAttribute(name, String(value))
        }
      }
      apply(node.attrs)
      return {
        dom,
        contentDOM: dom,
        update: next => {
          if (next.type !== current.type) return false
          current = next
          apply(next.attrs)
          return true
        },
        ignoreMutation: mutation => mutation.type === 'attributes' && mutation.target === dom,
      }
    }
  },
})

/** The DOM attributes of an element paragraph. */
function elementAttributes(attrs: Record<string, unknown>): { class: string; 'data-type': string; 'data-block-id'?: number } {
  const type = String(attrs.element_type)
  return {
    class: `script-el ${type}${attrs.is_dual ? ' dual' : ''}${attrs.origin && attrs.origin !== 'human' ? ' agent-authored' : ''}`,
    'data-type': type,
    ...(attrs.block_id ? { 'data-block-id': Number(attrs.block_id) } : {}),
  }
}

export const ColorMark = Mark.create({
  name: 'color',
  addAttributes() {
    return { color: { default: AMBER, parseHTML: (element: HTMLElement) => element.getAttribute('data-color') ?? AMBER } }
  },
  parseHTML() { return [{ tag: 'span[data-color]' }] },
  renderHTML({ mark }) {
    return ['span', { 'data-color': mark.attrs.color, class: 'script-color', style: `color: ${mark.attrs.color}` }, 0]
  },
})

/** The marks and nodes without behaviour: enough to build and serialise documents (tests use this). */
export function schemaExtensions(): Extension[] {
  return [ScriptDoc, Act, BeatNote, Scene, SceneHeading, Element, Text, Bold, Italic, Underline, Strike, ColorMark, UndoRedo] as unknown as Extension[]
}
