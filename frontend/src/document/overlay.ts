/**
 * Decorations over the document: accessible names for every element, inline agent proposals with
 * Accept / Reject / Roll back, *Keep mine / Load theirs* conflict bars, and collapsed acts.
 *
 * Nothing here changes the document: a proposal only lands when the writer accepts it.
 */
import { Extension } from '@tiptap/core'
import type { Node as PMNode } from '@tiptap/pm/model'
import { Plugin, PluginKey, type EditorState } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { AgentProposal } from '../api'
import type { ConflictReason } from './sync'
import { elementText } from './convert'
import { ELEMENT_LABELS } from './schema'

export type OverlayActions = {
  accept: (proposalId: number) => void
  reject: (proposalId: number) => void
  rollback: (proposalId: number) => void
  keepMine: (sceneId: number) => void
  loadTheirs: (sceneId: number) => void
  toggleAct: (actId: number) => void
}
export type OverlayState = {
  proposals: AgentProposal[]
  conflicts: ReadonlyMap<number, ConflictReason>
  collapsed: ReadonlySet<number>
  busy: ReadonlySet<number>
}
export const overlayKey = new PluginKey<{ overlay: OverlayState; decorations: DecorationSet }>('scriptOverlay')
const EMPTY: OverlayState = { proposals: [], conflicts: new Map(), collapsed: new Set(), busy: new Set() }

export type DiffPart = { kind: 'same' | 'insert' | 'delete'; text: string }

/** A word-level diff from `before` to `after` (longest common subsequence over words and spaces). */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/).filter(Boolean)
  const b = after.split(/(\s+)/).filter(Boolean)
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i -= 1) for (let j = b.length - 1; j >= 0; j -= 1) {
    table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
  }
  const parts: DiffPart[] = []
  const push = (kind: DiffPart['kind'], text: string) => {
    const last = parts[parts.length - 1]
    if (last?.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { push('same', a[i]); i += 1; j += 1 }
    else if (table[i + 1][j] >= table[i][j + 1]) { push('delete', a[i]); i += 1 }
    else { push('insert', b[j]); j += 1 }
  }
  while (i < a.length) { push('delete', a[i]); i += 1 }
  while (j < b.length) { push('insert', b[j]); j += 1 }
  return parts
}

/** Describe who proposed a change, for the margin. */
export function proposalAuthor(proposal: AgentProposal): string {
  const role = proposal.diff?.role ?? proposal.diff?.agent
  return typeof role === 'string' && role ? role.replace(/_/g, ' ') : 'Agent'
}

function button(label: string, className: string, onClick: () => void, name = label): HTMLButtonElement {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = className
  element.textContent = label
  element.setAttribute('aria-label', name)
  element.addEventListener('mousedown', event => event.preventDefault())
  element.addEventListener('click', event => { event.preventDefault(); onClick() })
  return element
}

function diffLine(before: string, after: string, type?: string): HTMLElement {
  const line = document.createElement('p')
  line.className = `proposal-line${type ? ` ${type}` : ''}`
  for (const part of wordDiff(before, after)) {
    const span = document.createElement(part.kind === 'insert' ? 'ins' : part.kind === 'delete' ? 'del' : 'span')
    span.textContent = part.text
    line.appendChild(span)
  }
  return line
}

function proposalCard(proposal: AgentProposal, body: HTMLElement[], actions: OverlayActions, busy: boolean): HTMLElement {
  const card = document.createElement('div')
  card.className = 'proposal-inline'
  card.setAttribute('contenteditable', 'false')
  card.setAttribute('role', 'group')
  card.setAttribute('aria-label', `Proposal ${proposal.id} from ${proposalAuthor(proposal)}`)
  const meta = document.createElement('div')
  meta.className = 'proposal-inline-meta'
  const who = document.createElement('strong')
  who.textContent = proposalAuthor(proposal)
  const summary = document.createElement('span')
  summary.textContent = String(proposal.diff?.summary ?? `Suggested change #${proposal.id}`)
  meta.append(who, summary)
  card.append(meta, ...body)
  const row = document.createElement('div')
  row.className = 'proposal-inline-actions'
  const accept = button('Accept', 'button primary', () => actions.accept(proposal.id), `Accept proposal ${proposal.id}`)
  const reject = button('Reject', 'button quiet', () => actions.reject(proposal.id), `Reject proposal ${proposal.id}`)
  if (busy) {
    accept.disabled = true
    accept.title = 'Save your edits to this scene first; the proposal was written against the saved version.'
  }
  row.append(accept, reject)
  card.append(row)
  return card
}

function rollbackChip(proposal: AgentProposal, actions: OverlayActions): HTMLElement {
  const chip = document.createElement('div')
  chip.className = 'proposal-applied'
  chip.setAttribute('contenteditable', 'false')
  chip.setAttribute('role', 'group')
  chip.setAttribute('aria-label', `Accepted proposal ${proposal.id}`)
  const label = document.createElement('span')
  label.textContent = `${proposalAuthor(proposal)} change accepted`
  chip.append(label, button('Roll back', 'mini-button', () => actions.rollback(proposal.id), `Roll back proposal ${proposal.id}`))
  return chip
}

function conflictBar(sceneId: number, reason: ConflictReason, actions: OverlayActions): HTMLElement {
  const bar = document.createElement('div')
  bar.className = 'scene-conflict'
  bar.setAttribute('contenteditable', 'false')
  bar.setAttribute('role', 'alert')
  const text = document.createElement('span')
  text.textContent = reason === 'stale' ? 'This scene was saved elsewhere before your edits.' : 'Changed elsewhere while you were editing.'
  bar.append(text,
    button('Keep mine', 'button primary', () => actions.keepMine(sceneId)),
    button('Load theirs', 'button quiet', () => actions.loadTheirs(sceneId)))
  return bar
}

type Proposed = { element_type?: string; text?: string }

/** Build every decoration for the document and the overlay state. */
export function buildDecorations(doc: PMNode, overlay: OverlayState, actions: OverlayActions): DecorationSet {
  const decorations: Decoration[] = []
  const counts = new Map<string, number>()
  let headings = 0
  const pendingBlocks = new Map<number, AgentProposal>()
  const pendingScenes = new Map<number, AgentProposal>()
  const approved = new Map<number, AgentProposal>()
  for (const proposal of overlay.proposals) {
    if (proposal.status === 'proposed' && proposal.target_kind === 'block') pendingBlocks.set(proposal.target_id, proposal)
    if (proposal.status === 'proposed' && proposal.target_kind === 'scene') pendingScenes.set(proposal.target_id, proposal)
    if (proposal.status === 'approved' && (proposal.target_kind === 'block' || proposal.target_kind === 'scene')) approved.set(proposal.id, proposal)
  }
  doc.descendants((node, pos, parent) => {
    const name = node.type.name
    if (name === 'act') {
      if (overlay.collapsed.has(Number(node.attrs.act_id))) decorations.push(Decoration.node(pos, pos + node.nodeSize, { class: 'act-collapsed' }))
      return true
    }
    if (name === 'scene') {
      const sceneId = Number(node.attrs.scene_id)
      const conflict = overlay.conflicts.get(sceneId)
      if (conflict) decorations.push(Decoration.widget(pos + 1, () => conflictBar(sceneId, conflict, actions), { side: -1, key: `conflict-${sceneId}-${conflict}`, ignoreSelection: true, stopEvent: () => true }))
      const proposal = pendingScenes.get(sceneId)
      if (proposal) {
        const operation = proposal.operation as { heading?: string; blocks?: Proposed[] }
        const current = [] as string[]
        node.forEach(child => { if (child.type.name === 'element') current.push(elementText(child)) })
        const lines: HTMLElement[] = []
        if (typeof operation.heading === 'string' && operation.heading !== node.child(0).textContent) lines.push(diffLine(node.child(0).textContent, operation.heading, 'heading'))
        if (Array.isArray(operation.blocks)) {
          operation.blocks.forEach((block, index) => lines.push(diffLine(current[index] ?? '', String(block.text ?? ''), block.element_type)))
          for (let index = operation.blocks.length; index < current.length; index += 1) lines.push(diffLine(current[index], ''))
          node.forEach((child, offset) => {
            if (child.type.name === 'element') decorations.push(Decoration.node(pos + 1 + offset, pos + 1 + offset + child.nodeSize, { class: 'proposal-replaced' }))
          })
        }
        decorations.push(Decoration.widget(pos + node.nodeSize - 1, () => proposalCard(proposal, lines, actions, overlay.busy.has(sceneId)), {
          side: 1, key: `proposal-${proposal.id}-${overlay.busy.has(sceneId)}`, ignoreSelection: true, stopEvent: () => true,
        }))
      }
      return true
    }
    if (name === 'sceneHeading') {
      headings += 1
      decorations.push(Decoration.node(pos, pos + node.nodeSize, { role: 'textbox', 'aria-label': `Scene heading ${headings}` }))
      return false
    }
    if (name !== 'element') return false
    const type = String(node.attrs.element_type)
    const count = (counts.get(type) ?? 0) + 1
    counts.set(type, count)
    decorations.push(Decoration.node(pos, pos + node.nodeSize, { role: 'textbox', 'aria-label': `${ELEMENT_LABELS[type] ?? type} ${count}` }))
    const blockId = node.attrs.block_id as number | null
    const pending = blockId !== null ? pendingBlocks.get(blockId) : undefined
    if (pending) {
      const operation = pending.operation as Proposed
      const before = elementText(node)
      const line = diffLine(before, typeof operation.text === 'string' ? operation.text : before, operation.element_type ?? type)
      const retype = operation.element_type && operation.element_type !== type ? [Object.assign(document.createElement('p'), { className: 'proposal-retype', textContent: `${ELEMENT_LABELS[type] ?? type} → ${ELEMENT_LABELS[operation.element_type] ?? operation.element_type}` })] : []
      const sceneId = Number(parent?.attrs.scene_id)
      decorations.push(Decoration.node(pos, pos + node.nodeSize, { class: 'proposal-target' }))
      decorations.push(Decoration.widget(pos + node.nodeSize, () => proposalCard(pending, [...retype, line], actions, overlay.busy.has(sceneId)), {
        side: 1, key: `proposal-${pending.id}-${overlay.busy.has(sceneId)}-${before}`, ignoreSelection: true, stopEvent: () => true,
      }))
    }
    const origin = String(node.attrs.origin ?? '')
    const applied = origin.startsWith('proposal:') ? approved.get(Number(origin.slice('proposal:'.length))) : undefined
    if (applied) decorations.push(Decoration.widget(pos + node.nodeSize, () => rollbackChip(applied, actions), { side: 1, key: `applied-${applied.id}`, ignoreSelection: true, stopEvent: () => true }))
    return false
  })
  return DecorationSet.create(doc, decorations)
}

/** Read the overlay state of an editor. */
export function overlayOf(state: EditorState): OverlayState {
  return overlayKey.getState(state)?.overlay ?? EMPTY
}

/** The overlay extension; update it with `tr.setMeta(overlayKey, partialState)`. */
export const ScriptOverlay = Extension.create<{ actions: { current: OverlayActions } }>({
  name: 'scriptOverlay',
  addOptions() {
    const noop = () => undefined
    return { actions: { current: { accept: noop, reject: noop, rollback: noop, keepMine: noop, loadTheirs: noop, toggleAct: noop } } }
  },
  addProseMirrorPlugins() {
    const actions: OverlayActions = {
      accept: id => this.options.actions.current.accept(id),
      reject: id => this.options.actions.current.reject(id),
      rollback: id => this.options.actions.current.rollback(id),
      keepMine: id => this.options.actions.current.keepMine(id),
      loadTheirs: id => this.options.actions.current.loadTheirs(id),
      toggleAct: id => this.options.actions.current.toggleAct(id),
    }
    return [new Plugin({
      key: overlayKey,
      state: {
        init: (_config, state) => ({ overlay: EMPTY, decorations: buildDecorations(state.doc, EMPTY, actions) }),
        apply: (tr, value, _old, state) => {
          const change = tr.getMeta(overlayKey) as Partial<OverlayState> | undefined
          if (!change && !tr.docChanged) return value
          const overlay = change ? { ...value.overlay, ...change } : value.overlay
          return { overlay, decorations: buildDecorations(state.doc, overlay, actions) }
        },
      },
      props: {
        decorations: state => overlayKey.getState(state)?.decorations,
        handleDOMEvents: {
          mousedown: (_view, event) => {
            const toggle = (event.target as HTMLElement | null)?.closest?.('.act-toggle')
            if (!toggle) return false
            event.preventDefault()
            const actId = Number(toggle.closest('[data-act-id]')?.getAttribute('data-act-id'))
            if (actId) actions.toggleAct(actId)
            return true
          },
        },
      },
    })]
  },
})
