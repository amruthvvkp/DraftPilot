/**
 * Saving and live sync for the document editor.
 *
 * Edits mark their scene dirty; about a second after the writer stops typing each dirty scene is sent
 * once through `PUT …/scenes/{id}/content` with `If-Match`. Server changes replace clean scenes in
 * place; a scene with unsaved edits (or a 409 on save) gets a *Keep mine / Load theirs* conflict
 * instead of being overwritten.
 */
import type { Editor, JSONContent } from '@tiptap/core'
import { type Node as PMNode } from '@tiptap/pm/model'
import { TextSelection, type Transaction } from '@tiptap/pm/state'
import { ApiError, type ProjectWorkspace, type Scene, type SceneContentResult } from '../api'
import type { Beat } from '../storyApi'
import { REMOTE } from './behaviour'
import { buildDoc, type SceneContent, sceneJSON, sceneNodes, serializeScene, type ServerBlock, structureKey } from './convert'

export type SyncApi = {
  write: (sceneId: number, version: number, content: SceneContent) => Promise<SceneContentResult>
  /** Fetch the newest workspace (after a 409), so *Load theirs* and *Keep mine* see what changed. */
  refresh: () => void
}
export type ConflictReason = 'remote' | 'stale'
export type SyncStatus = 'saved' | 'unsaved' | 'saving' | 'error'
export type SyncSnapshot = { status: SyncStatus; error: string; conflicts: ReadonlyMap<number, ConflictReason>; busy: ReadonlySet<number> }
type Snapshot = { workspace: Pick<ProjectWorkspace, 'acts' | 'scenes'> & { blocks: Record<number, ServerBlock[]> }; beats: Beat[] }

/** A cursor position that survives a reload: an element's uid, or a scene heading, plus an offset. */
type Anchor = { uid: string; offset: number } | { sceneId: number; offset: number } | null

function anchorAt(doc: PMNode, pos: number): Anchor {
  const $pos = doc.resolve(pos)
  const parent = $pos.parent
  if (parent.type.name === 'element' && parent.attrs.uid) return { uid: String(parent.attrs.uid), offset: $pos.parentOffset }
  if (parent.type.name === 'sceneHeading') return { sceneId: Number($pos.node($pos.depth - 1).attrs.scene_id), offset: $pos.parentOffset }
  return null
}

function resolveAnchor(doc: PMNode, anchor: Anchor): number | null {
  if (!anchor) return null
  let found: number | null = null
  doc.descendants((node, pos) => {
    if (found !== null) return false
    if ('uid' in anchor && node.type.name === 'element' && node.attrs.uid === anchor.uid) found = pos + 1 + Math.min(anchor.offset, node.content.size)
    if ('sceneId' in anchor && node.type.name === 'scene' && node.attrs.scene_id === anchor.sceneId) {
      const heading = node.child(0)
      found = pos + 2 + Math.min(anchor.offset, heading.content.size)
    }
    return found === null && node.type.name !== 'element' && node.type.name !== 'sceneHeading'
  })
  return found
}

/** Every block id in the document mapped to its element's uid, so reloaded nodes keep their identity. */
function uidsByBlock(doc: PMNode): Map<number, string> {
  const uids = new Map<number, string>()
  doc.descendants(node => {
    if (node.type.name === 'element') { if (node.attrs.block_id && node.attrs.uid) uids.set(Number(node.attrs.block_id), String(node.attrs.uid)); return false }
    return true
  })
  return uids
}

/**
 * Read any DOM change ProseMirror hasn't seen yet. Keyboard selection changes reach it
 * asynchronously, so a server-side transaction landing between a Shift+Arrow and that read would
 * put the old selection back. Call this before building a remote transaction.
 */
export function flushPendingDOM(editor: Editor): void {
  const observer = (editor.view as unknown as { domObserver?: { flush?: () => void } }).domObserver
  try { observer?.flush?.() } catch { /* best effort: an unflushed selection only costs a keystroke */ }
}

/** Dispatch a server-side change: no dirty tracking, no undo step. */
export function dispatchRemote(editor: Editor, tr: Transaction): void {
  editor.view.dispatch(tr.setMeta(REMOTE, true).setMeta('addToHistory', false))
}

export class DocumentSync {
  /** The scene that owns each block id, as the server last said. */
  readonly owners = new Map<number, number>()
  private readonly versions = new Map<number, number>()
  private readonly dirty = new Set<number>()
  private readonly revisions = new Map<number, number>()
  private readonly inFlight = new Set<number>()
  private readonly sent = new Map<number, string>()
  private conflicts = new Map<number, ConflictReason>()
  private server: Snapshot | null = null
  private editor: Editor | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private error = ''
  private snapshot: SyncSnapshot = { status: 'saved', error: '', conflicts: new Map(), busy: new Set() }
  private readonly listeners = new Set<() => void>()

  constructor(private readonly api: SyncApi, private readonly delay = 1000) {}

  /** Remember the server state the editor was built from. */
  init(workspace: Snapshot['workspace'], beats: Beat[]): void {
    this.server = { workspace, beats }
    for (const scene of workspace.scenes) this.adopt(scene, workspace.blocks[scene.id] ?? [])
  }

  /** Connect the editor this controller saves and reloads. */
  attach(editor: Editor): void {
    this.editor = editor
    for (const { node } of sceneNodes(editor.state.doc).values()) this.rememberSent(node)
  }

  /** Stop saving with this editor (it is going away); pending edits are flushed first. */
  async detach(editor: Editor): Promise<void> {
    if (this.editor !== editor) return
    await this.flush()
    // A remount may have attached a new editor while the flush ran.
    if (this.editor === editor) this.editor = null
  }

  /** The current save state, for `useSyncExternalStore`. */
  getSnapshot = (): SyncSnapshot => this.snapshot

  /** Listen for save-state changes. */
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  /** True while a scene has edits the server hasn't stored. */
  isDirty(sceneId: number): boolean {
    return this.dirty.has(sceneId) || this.inFlight.has(sceneId)
  }

  /** The version the editor last saw for a scene. */
  versionOf(sceneId: number): number | undefined {
    return this.versions.get(sceneId)
  }

  private emit(): void {
    const status: SyncStatus = this.error ? 'error' : this.inFlight.size ? 'saving' : this.dirty.size ? 'unsaved' : 'saved'
    const busy = new Set([...this.dirty, ...this.inFlight])
    const same = <T>(a: ReadonlySet<T> | ReadonlyMap<T, unknown>, b: ReadonlySet<T> | ReadonlyMap<T, unknown>) =>
      a.size === b.size && [...a.keys()].every(key => b.has(key) && (!(a instanceof Map) || a.get(key) === (b as ReadonlyMap<T, unknown>).get(key)))
    const previous = this.snapshot
    // Only a real change notifies listeners, so typing doesn't re-render the page on every key.
    if (previous.status === status && previous.error === this.error && same(previous.conflicts, this.conflicts) && same(previous.busy, busy)) return
    this.snapshot = { status, error: this.error, conflicts: new Map(this.conflicts), busy }
    this.listeners.forEach(listener => listener())
  }

  private adopt(scene: Pick<Scene, 'id' | 'version'>, blocks: { id: number }[]): void {
    this.versions.set(scene.id, scene.version)
    for (const [blockId, owner] of [...this.owners]) if (owner === scene.id) this.owners.delete(blockId)
    for (const block of blocks) this.owners.set(block.id, scene.id)
  }

  private rememberSent(node: PMNode): void {
    const { sceneId, content } = serializeScene(node, id => this.owners.get(id) === Number(node.attrs.scene_id))
    this.sent.set(sceneId, JSON.stringify(content))
  }

  /** Record a local edit: compare scene nodes before and after (untouched scenes keep their node). */
  noteChange(before: PMNode, after: PMNode): void {
    const old = sceneNodes(before)
    let changed = false
    for (const [sceneId, { node }] of sceneNodes(after)) {
      if (old.get(sceneId)?.node === node) continue
      this.dirty.add(sceneId)
      this.revisions.set(sceneId, (this.revisions.get(sceneId) ?? 0) + 1)
      changed = true
    }
    if (!changed) return
    this.emit()
    this.schedule()
  }

  private schedule(delay = this.delay): void {
    if (this.timer) clearTimeout(this.timer)
    this.timer = setTimeout(() => { this.timer = null; void this.flush() }, delay)
  }

  /** Send every dirty scene now (one request per scene). */
  async flush(): Promise<void> {
    if (this.timer) { clearTimeout(this.timer); this.timer = null }
    await Promise.all([...this.dirty].filter(id => !this.inFlight.has(id) && !this.conflicts.has(id)).map(id => this.save(id)))
  }

  private async save(sceneId: number): Promise<void> {
    const editor = this.editor
    const entry = editor && sceneNodes(editor.state.doc).get(sceneId)
    if (!editor || !entry) { this.dirty.delete(sceneId); this.emit(); return }
    const serialized = serializeScene(entry.node, id => this.owners.get(id) === sceneId)
    const body = JSON.stringify(serialized.content)
    const revision = this.revisions.get(sceneId) ?? 0
    if (body === this.sent.get(sceneId)) { this.dirty.delete(sceneId); this.emit(); return }
    this.inFlight.add(sceneId)
    this.dirty.delete(sceneId)
    this.emit()
    try {
      const result = await this.api.write(sceneId, this.versions.get(sceneId) ?? 0, serialized.content)
      this.error = ''
      this.sent.set(sceneId, body)
      this.versions.set(sceneId, result.version)
      for (const [blockId, owner] of [...this.owners]) if (owner === sceneId) this.owners.delete(blockId)
      result.block_ids.forEach(id => this.owners.set(id, sceneId))
      this.writeBack(sceneId, serialized.uids, result.block_ids, serialized.content)
      if ((this.revisions.get(sceneId) ?? 0) !== revision) this.dirty.add(sceneId)
    } catch (reason) {
      this.dirty.add(sceneId)
      if (reason instanceof ApiError && reason.status === 409) {
        this.conflicts.set(sceneId, 'stale')
        this.api.refresh()
      } else {
        this.error = reason instanceof Error ? reason.message : 'Unable to save the scene'
        this.schedule(5000)
      }
    } finally {
      this.inFlight.delete(sceneId)
      this.emit()
    }
    if (this.dirty.has(sceneId) && !this.conflicts.has(sceneId)) this.schedule()
    if (this.server) this.reconcile(this.server.workspace, this.server.beats)
  }

  /** Write the server's block ids (and the text it stored) back into the elements that were sent. */
  private writeBack(sceneId: number, uids: string[], blockIds: number[], content: SceneContent): void {
    const editor = this.editor
    if (!editor) return
    flushPendingDOM(editor)
    const byUid = new Map(uids.map((uid, index) => [uid, { id: blockIds[index], text: content.blocks[index].text }]))
    const entry = sceneNodes(editor.state.doc).get(sceneId)
    if (!entry) return
    const tr = editor.state.tr
    entry.node.descendants((node, offset) => {
      const saved = node.type.name === 'element' ? byUid.get(String(node.attrs.uid)) : undefined
      if (saved && (node.attrs.block_id !== saved.id || node.attrs.source !== saved.text)) {
        tr.setNodeMarkup(entry.pos + 1 + offset, undefined, { ...node.attrs, block_id: saved.id, source: saved.text })
      }
      return false
    })
    if (tr.docChanged) dispatchRemote(editor, tr)
  }

  /**
   * Fold the newest server state into the document. A scene the server has moved past is replaced
   * when it's clean, or flagged when it has local edits; anything structural (scenes added, removed
   * or moved, beats changed) rebuilds the document around the local scenes.
   */
  reconcile(workspace: Snapshot['workspace'], beats: Beat[]): void {
    this.server = { workspace, beats }
    const editor = this.editor
    if (!editor || editor.isDestroyed) return
    flushPendingDOM(editor)
    const doc = editor.state.doc
    const current = sceneNodes(doc)
    const replace = new Set<number>()
    for (const scene of workspace.scenes) {
      if (!current.has(scene.id)) { replace.add(scene.id); continue }
      if (scene.version <= (this.versions.get(scene.id) ?? 0) || this.inFlight.has(scene.id)) continue
      if (this.dirty.has(scene.id) || this.conflicts.has(scene.id)) { if (!this.conflicts.has(scene.id)) this.conflicts.set(scene.id, 'remote'); continue }
      replace.add(scene.id)
    }
    const stub = (scene: Scene): JSONContent | undefined => replace.has(scene.id) ? undefined : { type: 'scene', attrs: { scene_id: scene.id } }
    const uids = uidsByBlock(doc)
    const sameShape = structureKey(buildDoc(workspace, beats, { keep: stub })) === structureKey(doc)
    const anchor = anchorAt(doc, editor.state.selection.anchor)
    const head = anchorAt(doc, editor.state.selection.head)
    const tr = editor.state.tr
    if (sameShape) {
      for (const sceneId of replace) {
        const scene = workspace.scenes.find(item => item.id === sceneId)!
        const target = sceneNodes(tr.doc).get(sceneId)!
        tr.replaceWith(target.pos, target.pos + target.node.nodeSize, editor.schema.nodeFromJSON(sceneJSON(scene, workspace.blocks[sceneId] ?? [], uids)))
      }
      this.syncOutline(tr, workspace, beats)
    } else {
      const keep = (scene: Scene) => replace.has(scene.id) ? undefined : current.get(scene.id)?.node.toJSON() as JSONContent | undefined
      const rebuilt = editor.schema.nodeFromJSON(buildDoc(workspace, beats, { keep, uids }))
      tr.replaceWith(0, doc.content.size, rebuilt.content)
    }
    for (const sceneId of replace) {
      const scene = workspace.scenes.find(item => item.id === sceneId)!
      this.adopt(scene, workspace.blocks[sceneId] ?? [])
      this.dirty.delete(sceneId)
    }
    const known = new Set(workspace.scenes.map(scene => scene.id))
    for (const sceneId of [...this.versions.keys()]) if (!known.has(sceneId)) { this.versions.delete(sceneId); this.dirty.delete(sceneId); this.conflicts.delete(sceneId) }
    if (tr.docChanged) {
      const from = resolveAnchor(tr.doc, anchor)
      const to = resolveAnchor(tr.doc, head)
      if (from !== null && to !== null) tr.setSelection(TextSelection.create(tr.doc, from, to))
      dispatchRemote(editor, tr)
      for (const sceneId of replace) { const entry = sceneNodes(editor.state.doc).get(sceneId); if (entry) this.rememberSent(entry.node) }
    }
    this.emit()
  }

  /** Update act titles and beat notes in place when only their text changed. */
  private syncOutline(tr: Transaction, workspace: Snapshot['workspace'], beats: Beat[]): void {
    const beatById = new Map(beats.map(beat => [beat.id, beat]))
    const actById = new Map(workspace.acts.map(act => [act.id, act]))
    tr.doc.descendants((node, pos) => {
      if (node.type.name === 'act') {
        const act = actById.get(Number(node.attrs.act_id))
        const title = act ? act.title || `Act ${act.position + 1}` : node.attrs.title
        if (title !== node.attrs.title) tr.setNodeMarkup(pos, undefined, { ...node.attrs, title })
        return true
      }
      if (node.type.name === 'beatNote') {
        const beat = beatById.get(Number(node.attrs.beat_id))
        if (beat && (beat.title !== node.attrs.title || beat.summary !== node.attrs.summary || beat.version !== node.attrs.version)) {
          tr.setNodeMarkup(pos, undefined, { ...node.attrs, title: beat.title, summary: beat.summary, version: beat.version })
        }
      }
      return false
    })
  }

  /** Resolve a conflict by keeping the local scene: save it over the server's version. */
  keepMine(sceneId: number): void {
    const scene = this.server?.workspace.scenes.find(item => item.id === sceneId)
    if (scene) this.adopt(scene, this.server?.workspace.blocks[sceneId] ?? [])
    this.conflicts.delete(sceneId)
    this.sent.delete(sceneId)
    this.dirty.add(sceneId)
    this.emit()
    void this.flush()
  }

  /** Resolve a conflict by dropping the local edits and loading the server's scene. */
  loadTheirs(sceneId: number): void {
    this.conflicts.delete(sceneId)
    this.dirty.delete(sceneId)
    this.versions.set(sceneId, -1)
    if (this.server) this.reconcile(this.server.workspace, this.server.beats)
  }
}
