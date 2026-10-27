/** Convert between the workspace payload (scenes, blocks, beats) and the editor's document. */
import type { JSONContent } from '@tiptap/core'
import type { Node as PMNode } from '@tiptap/pm/model'
import type { ProjectWorkspace, Scene, ScreenplayBlock } from '../api'
import type { Beat } from '../storyApi'
import { type MarkName, parseInline, type Run, sameRuns, serializeInline } from './fountain'
import { newUid } from './schema'

export type ServerBlock = Pick<ScreenplayBlock, 'id' | 'element_type' | 'text' | 'is_dual' | 'dual_group' | 'character_extension'> & { origin?: string; position?: number }
export type ContentBlock = { id?: number; element_type: string; text: string; is_dual: boolean; dual_group: number | null; character_extension: string | null }
export type SceneContent = { heading: string; blocks: ContentBlock[] }

/** Turn Fountain text into the editor's inline content. */
export function inlineContent(text: string): JSONContent[] {
  return parseInline(text).map(run => ({
    type: 'text', text: run.text,
    ...(run.marks.length ? { marks: run.marks.map(mark => mark.attrs ? { type: mark.type, attrs: mark.attrs } : { type: mark.type }) } : {}),
  }))
}

/** One block as an `element` node; `uid` keeps a node's identity when the block is reloaded. */
export function elementJSON(block: ServerBlock, uid: string = newUid()): JSONContent {
  return {
    type: 'element',
    attrs: {
      uid, block_id: block.id, element_type: block.element_type, origin: block.origin ?? 'human',
      is_dual: block.is_dual, dual_group: block.dual_group, character_extension: block.character_extension, source: block.text,
    },
    content: inlineContent(block.text),
  }
}

/** One scene with its heading and blocks (in position order); `uids` reuses identities by block id. */
export function sceneJSON(scene: Pick<Scene, 'id' | 'heading' | 'version'>, blocks: ServerBlock[], uids: Map<number, string> = new Map()): JSONContent {
  const ordered = [...blocks].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
  return {
    type: 'scene',
    attrs: { scene_id: scene.id, version: scene.version },
    content: [
      { type: 'sceneHeading', ...(scene.heading ? { content: [{ type: 'text', text: scene.heading }] } : {}) },
      ...ordered.map(block => elementJSON(block, uids.get(block.id))),
    ],
  }
}

export type ActItem = { kind: 'beat'; beat: Beat; linked: boolean } | { kind: 'scene'; scene: Scene }

/**
 * Lay out one act: each linked beat sits above the first of its scenes, and a beat with no scene yet
 * sits after the scenes of the beat before it (or at the top of the act), as a placeholder.
 */
export function layoutAct(scenes: Scene[], beats: Beat[]): ActItem[] {
  const ordered = [...scenes].sort((a, b) => a.position - b.position)
  const index = new Map(ordered.map((scene, at) => [scene.id, at]))
  const before = new Map<number, Beat[]>()
  const after = new Map<number, Beat[]>()
  const top: Beat[] = []
  let lastLinked = -1
  for (const beat of [...beats].sort((a, b) => a.position - b.position)) {
    const linked = beat.scene_ids.map(id => index.get(id)).filter((at): at is number => at !== undefined)
    if (linked.length) {
      const first = Math.min(...linked)
      before.set(first, [...(before.get(first) ?? []), beat])
      lastLinked = Math.max(...linked)
    } else if (lastLinked < 0) top.push(beat)
    else after.set(lastLinked, [...(after.get(lastLinked) ?? []), beat])
  }
  const items: ActItem[] = top.map(beat => ({ kind: 'beat', beat, linked: false }))
  ordered.forEach((scene, at) => {
    for (const beat of before.get(at) ?? []) items.push({ kind: 'beat', beat, linked: true })
    items.push({ kind: 'scene', scene })
    for (const beat of after.get(at) ?? []) items.push({ kind: 'beat', beat, linked: false })
  })
  return items
}

/** Decide which act a beat belongs to in this draft, or null when its scenes are all in another draft. */
function beatAct(beat: Beat, sceneActs: Map<number, number>, firstAct: number): number | null {
  if (beat.scene_ids.length === 0) return beat.act_id !== null && beat.act_id !== undefined && [...sceneActs.values(), firstAct].includes(beat.act_id) ? beat.act_id : firstAct
  const act = beat.scene_ids.map(id => sceneActs.get(id)).find(id => id !== undefined)
  return act ?? null
}

export type BuildOptions = {
  /** Return the current node JSON for a scene that must not be replaced (dirty, saving, or up to date). */
  keep?: (scene: Scene) => JSONContent | undefined
  /** Reuse element identities by block id, so the cursor survives a reload. */
  uids?: Map<number, string>
}

/** Build the whole draft as one document: acts, inline beats and scenes. */
export function buildDoc(workspace: Pick<ProjectWorkspace, 'acts' | 'scenes'> & { blocks: Record<number, ServerBlock[]> }, beats: Beat[] = [], options: BuildOptions = {}): JSONContent {
  const acts = [...workspace.acts].sort((a, b) => a.position - b.position)
  const sceneActs = new Map(workspace.scenes.map(scene => [scene.id, scene.act_id]))
  const firstAct = acts[0]?.id ?? 0
  return {
    type: 'doc',
    content: acts.map(act => {
      const scenes = workspace.scenes.filter(scene => scene.act_id === act.id)
      const actBeats = beats.filter(beat => beatAct(beat, sceneActs, firstAct) === act.id)
      return {
        type: 'act',
        attrs: { act_id: act.id, title: act.title || `Act ${act.position + 1}` },
        content: layoutAct(scenes, actBeats).map(item => item.kind === 'beat'
          ? { type: 'beatNote', attrs: { beat_id: item.beat.id, version: item.beat.version, title: item.beat.title, summary: item.beat.summary, act_id: act.id, linked: item.linked } }
          : options.keep?.(item.scene) ?? sceneJSON(item.scene, workspace.blocks[item.scene.id] ?? [], options.uids)),
      }
    }),
  }
}

/** Read an element's text runs with their marks. */
export function runsOf(node: PMNode): Run[] {
  const runs: Run[] = []
  node.forEach(child => {
    runs.push({
      text: child.text ?? '',
      marks: child.marks.map(mark => mark.type.name === 'color' ? { type: 'color' as const, attrs: { color: String(mark.attrs.color) } } : { type: mark.type.name as MarkName }),
    })
  })
  return runs
}

/** Serialise one element's text to Fountain, reusing the server's text verbatim when nothing changed. */
export function elementText(node: PMNode): string {
  const source = node.attrs.source as string | null
  const runs = runsOf(node)
  if (source !== null && sameRuns(runs, parseInline(source))) return source
  const typed = node.attrs.element_type === 'character' ? runs.map(run => ({ ...run, text: run.text.toUpperCase() })) : runs
  return serializeInline(typed)
}

export type SerializedScene = { sceneId: number; content: SceneContent; uids: string[]; newUids: string[] }

/**
 * Serialise a scene node for `PUT …/scenes/{id}/content`. A block id is only sent when this scene
 * owns it and no earlier element already used it; otherwise the element is posted as a new block.
 */
export function serializeScene(node: PMNode, owns: (blockId: number) => boolean = () => true): SerializedScene {
  const blocks: ContentBlock[] = []
  const uids: string[] = []
  const newUids: string[] = []
  const seen = new Set<number>()
  let heading = ''
  node.forEach(child => {
    if (child.type.name === 'sceneHeading') { heading = child.textContent; return }
    const id = child.attrs.block_id as number | null
    const keep = id !== null && owns(id) && !seen.has(id)
    if (keep) seen.add(id)
    else newUids.push(String(child.attrs.uid))
    uids.push(String(child.attrs.uid))
    blocks.push({
      ...(keep ? { id } : {}),
      element_type: String(child.attrs.element_type), text: elementText(child),
      is_dual: Boolean(child.attrs.is_dual), dual_group: (child.attrs.dual_group as number | null) ?? null,
      character_extension: (child.attrs.character_extension as string | null) ?? null,
    })
  })
  return { sceneId: Number(node.attrs.scene_id), content: { heading, blocks }, uids, newUids }
}

/** Find every scene node in a document with its position. */
export function sceneNodes(doc: PMNode): Map<number, { node: PMNode; pos: number }> {
  const scenes = new Map<number, { node: PMNode; pos: number }>()
  doc.descendants((node, pos) => {
    if (node.type.name === 'scene') { scenes.set(Number(node.attrs.scene_id), { node, pos }); return false }
    return node.type.name === 'doc' || node.type.name === 'act'
  })
  return scenes
}

/** The document's outline shape: acts, beats and scenes in order (a change means a rebuild). */
export function structureKey(doc: PMNode | JSONContent): string {
  const parts: string[] = []
  const label = (type: string | undefined, attrs: Record<string, unknown> | undefined) => {
    if (type === 'act') parts.push(`a${attrs?.act_id}`)
    if (type === 'beatNote') parts.push(`b${attrs?.beat_id}`)
    if (type === 'scene') parts.push(`s${attrs?.scene_id}`)
  }
  if ('forEach' in doc && typeof doc.forEach === 'function') {
    (doc as PMNode).forEach(act => { label('act', act.attrs); act.forEach(child => label(child.type.name, child.attrs)) })
  } else {
    for (const act of (doc as JSONContent).content ?? []) {
      label(act.type, act.attrs)
      for (const child of act.content ?? []) label(child.type, child.attrs)
    }
  }
  return parts.join(' ')
}
