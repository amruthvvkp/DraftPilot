import type { Act } from '../api'
import type { Beat, Character, StoryMoment, TimelineEvent } from '../storyApi'
import { byPosition } from '../project/order'

/** Narrative is when the audience sees a moment; chronology is when it happens in the story world. */
export type Axis = 'narrative' | 'chronology'

export type SceneLite = { id: number; act_id: number; heading: string; position: number }

export type JourneyData = {
  characters: Character[]
  events: TimelineEvent[]
  moments: StoryMoment[]
  acts: Act[]
  scenes: SceneLite[]
  beats: Beat[]
}

export type Column = {
  key: string
  index: number
  kind: 'scene' | 'beat' | 'chrono'
  label: string
  /** The act (narrative) the column sits in; null for chronology and act-less beats. */
  actId: number | null
  sceneId?: number
  beatId?: number
  chrono?: number
  /** Script number of a scene column in the applied order, when a proposed order moved it. */
  movedFrom?: number
  x: number
}

export type Lane = { character: Character; index: number; y: number; height: number }

export type PlacedCard = { event: TimelineEvent; lane: number; column: number; slot: number; x: number; y: number; ghost: boolean }

export type PlacedMoment = {
  moment: StoryMoment
  events: TimelineEvent[]
  /** Lane indexes of the participants, top to bottom. */
  lanes: number[]
  column: number
  slot: number
  x: number
  y: number
  height: number
  ghost: boolean
}

export type JourneyLayout = {
  axis: Axis
  columns: Column[]
  lanes: Lane[]
  cards: PlacedCard[]
  moments: PlacedMoment[]
  /** Events that have no place on this axis (the Unplaced tray). */
  unplaced: TimelineEvent[]
  /** Shared moments with no place on this axis. */
  unplacedMoments: StoryMoment[]
  width: number
  height: number
}

export const HEADER_WIDTH = 200
export const COLUMN_WIDTH = 220
export const CARD_WIDTH = 196
export const SLOT_HEIGHT = 132
export const CARD_HEIGHT = 120
export const LANE_PADDING = 12
export const TOP = 56
export const CAST_HEIGHT = 120

type Anchor = { kind: 'scene'; id: number } | { kind: 'beat'; id: number } | null

/** Return the cast in the room's order, or in `laneOrder` when given (unknown ids keep their order after). */
export function orderedCast(characters: Character[], laneOrder?: number[]): Character[] {
  const cast = byPosition(characters)
  if (!laneOrder?.length) return cast
  const rank = new Map(laneOrder.map((id, index) => [id, index]))
  return [...cast].sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity))
}

/** Return the scenes in script order: acts by position, then scenes by position. */
export function scriptOrder(acts: Act[], scenes: SceneLite[]): number[] {
  const actRank = new Map(acts.map(act => [act.id, act.position]))
  return [...scenes].sort((a, b) => (actRank.get(a.act_id) ?? 0) - (actRank.get(b.act_id) ?? 0) || a.position - b.position || a.id - b.id).map(scene => scene.id)
}

/** Build the narrative columns: per act, its scenes in `order`, then its beats that link no scene. */
function narrativeColumns(data: JourneyData, order: number[], baseOrder: number[]): Column[] {
  const sceneById = new Map(data.scenes.map(scene => [scene.id, scene]))
  const sceneIds = new Set(order)
  const acts = [...data.acts].sort((a, b) => a.position - b.position)
  const actIds = new Set(acts.map(act => act.id))
  const looseBeats = byPosition(data.beats.filter(beat => !beat.scene_ids.some(id => sceneIds.has(id))))
  const columns: Omit<Column, 'index' | 'x'>[] = []
  const actGroups: (number | null)[] = [...acts.map(act => act.id), null]
  for (const actId of actGroups) {
    if (actId !== null) {
      for (const sceneId of order) {
        const scene = sceneById.get(sceneId)
        if (scene?.act_id !== actId) continue
        const number = order.indexOf(sceneId) + 1
        const before = baseOrder.indexOf(sceneId) + 1
        columns.push({ key: `scene-${sceneId}`, kind: 'scene', label: `${number}. ${scene.heading}`, actId, sceneId, movedFrom: before && before !== number ? before : undefined })
      }
    }
    for (const beat of looseBeats) {
      const beatAct = beat.act_id !== null && actIds.has(beat.act_id) ? beat.act_id : null
      if (beatAct === actId) columns.push({ key: `beat-${beat.id}`, kind: 'beat', label: beat.title, actId, beatId: beat.id })
    }
  }
  return columns.map((column, index) => ({ ...column, index, x: HEADER_WIDTH + index * COLUMN_WIDTH }))
}

/** Where an event or moment sits in narrative order: its scene, else its beat. */
function anchorOf(sceneId: number | null, beatId: number | null): Anchor {
  if (sceneId !== null) return { kind: 'scene', id: sceneId }
  if (beatId !== null) return { kind: 'beat', id: beatId }
  return null
}

/** Resolve an anchor to a column index: a scene column, a loose beat's column, or a linked beat's first scene. */
function narrativeColumn(anchor: Anchor, columns: Column[], beats: Map<number, Beat>): number | null {
  if (!anchor) return null
  if (anchor.kind === 'scene') return columns.find(column => column.sceneId === anchor.id)?.index ?? null
  const own = columns.find(column => column.beatId === anchor.id)
  if (own) return own.index
  const linked = new Set(beats.get(anchor.id)?.scene_ids ?? [])
  return columns.find(column => column.sceneId !== undefined && linked.has(column.sceneId))?.index ?? null
}

type Item = { kind: 'event'; event: TimelineEvent; lane: number; column: number } | { kind: 'moment'; moment: StoryMoment; events: TimelineEvent[]; lanes: number[]; column: number }

/**
 * Lay the map out on one axis: lanes per character, columns per scene/beat (narrative) or story-world
 * position (chronology), each shared moment drawn once across its participants' lanes.
 * `order` is the scene order to show (a proposed order shows as ghosts against `baseOrder`).
 */
export function layoutJourney(data: JourneyData, axis: Axis, options: { order?: number[]; baseOrder?: number[]; laneOrder?: number[] } = {}): JourneyLayout {
  const cast = orderedCast(data.characters, options.laneOrder)
  const laneOf = new Map(cast.map((character, index) => [character.id, index]))
  const baseOrder = options.baseOrder ?? scriptOrder(data.acts, data.scenes)
  const order = options.order ?? baseOrder
  const momentById = new Map(data.moments.map(moment => [moment.id, moment]))
  const beats = new Map(data.beats.map(beat => [beat.id, beat]))
  const events = data.events.filter(event => laneOf.has(event.character_id))
  const participants = new Map<number, TimelineEvent[]>()
  const solo: TimelineEvent[] = []
  for (const event of events) {
    if (event.moment_id !== null && momentById.has(event.moment_id)) participants.set(event.moment_id, [...(participants.get(event.moment_id) ?? []), event])
    else solo.push(event)
  }
  const shared = data.moments.filter(moment => participants.has(moment.id))
  const unplacedMoments = data.moments.filter(moment => !participants.has(moment.id))

  let columns: Column[]
  const placeEvent = new Map<number, number | null>()
  const placeMoment = new Map<number, number | null>()
  if (axis === 'narrative') {
    columns = narrativeColumns(data, order, baseOrder)
    for (const event of solo) placeEvent.set(event.id, narrativeColumn(anchorOf(event.scene_id, event.beat_id), columns, beats))
    for (const moment of shared) {
      const first = participants.get(moment.id)?.find(event => event.scene_id !== null || event.beat_id !== null)
      const anchor = anchorOf(moment.scene_id, moment.beat_id) ?? (first ? anchorOf(first.scene_id, first.beat_id) : null)
      placeMoment.set(moment.id, narrativeColumn(anchor, columns, beats))
    }
  } else {
    const labels = new Map<number, string>()
    for (const event of solo) if (event.chrono_index !== null && !labels.get(event.chrono_index)) labels.set(event.chrono_index, event.story_time)
    for (const moment of shared) if (moment.chrono_index !== null && !labels.get(moment.chrono_index)) labels.set(moment.chrono_index, moment.story_time)
    const values = [...labels.keys()].sort((a, b) => a - b)
    columns = values.map((value, index) => ({ key: `chrono-${value}`, index, kind: 'chrono', label: labels.get(value) || `Point ${index + 1}`, actId: null, chrono: value, x: HEADER_WIDTH + index * COLUMN_WIDTH }))
    const at = new Map(values.map((value, index) => [value, index]))
    for (const event of solo) placeEvent.set(event.id, event.chrono_index === null ? null : at.get(event.chrono_index) ?? null)
    for (const moment of shared) placeMoment.set(moment.id, moment.chrono_index === null ? null : at.get(moment.chrono_index) ?? null)
  }

  const items: Item[] = []
  const unplaced: TimelineEvent[] = []
  for (const moment of shared) {
    const column = placeMoment.get(moment.id) ?? null
    const members = [...(participants.get(moment.id) ?? [])].sort((a, b) => (laneOf.get(a.character_id) ?? 0) - (laneOf.get(b.character_id) ?? 0))
    if (column === null) { unplacedMoments.push(moment); continue }
    items.push({ kind: 'moment', moment, events: members, lanes: [...new Set(members.map(event => laneOf.get(event.character_id) ?? 0))], column })
  }
  for (const event of byPosition(solo)) {
    const column = placeEvent.get(event.id) ?? null
    if (column === null) unplaced.push(event)
    else items.push({ kind: 'event', event, lane: laneOf.get(event.character_id) ?? 0, column })
  }

  // Stack items that share a cell: a moment takes the lowest slot free in every lane it spans.
  const taken = new Map<string, Set<number>>()
  const cell = (lane: number, column: number): Set<number> => {
    const key = `${lane}:${column}`
    if (!taken.has(key)) taken.set(key, new Set())
    return taken.get(key)!
  }
  const slotOf = new Map<Item, number>()
  for (const item of [...items].sort((a, b) => (a.kind === 'moment' ? 0 : 1) - (b.kind === 'moment' ? 0 : 1))) {
    const span = item.kind === 'moment' ? range(item.lanes[0], item.lanes[item.lanes.length - 1]) : [item.lane]
    let slot = 0
    while (span.some(lane => cell(lane, item.column).has(slot))) slot += 1
    for (const lane of span) cell(lane, item.column).add(slot)
    slotOf.set(item, slot)
  }
  const slotsInLane = cast.map((_, lane) => Math.max(1, ...[...taken.entries()].filter(([key]) => key.startsWith(`${lane}:`)).map(([, slots]) => Math.max(...slots) + 1)))
  const lanes: Lane[] = []
  let y = TOP
  cast.forEach((character, index) => {
    const height = slotsInLane[index] * SLOT_HEIGHT + LANE_PADDING * 2
    lanes.push({ character, index, y, height })
    y += height
  })
  const ghostColumns = new Set(columns.filter(column => column.movedFrom !== undefined).map(column => column.index))
  const cardY = (lane: number, slot: number): number => lanes[lane].y + LANE_PADDING + slot * SLOT_HEIGHT
  const cards: PlacedCard[] = []
  const moments: PlacedMoment[] = []
  for (const item of items) {
    const slot = slotOf.get(item) ?? 0
    const x = columns[item.column].x + (COLUMN_WIDTH - CARD_WIDTH) / 2
    const ghost = ghostColumns.has(item.column)
    if (item.kind === 'event') cards.push({ event: item.event, lane: item.lane, column: item.column, slot, x, y: cardY(item.lane, slot), ghost })
    else {
      const top = cardY(item.lanes[0], slot)
      const bottom = cardY(item.lanes[item.lanes.length - 1], slot) + CARD_HEIGHT
      moments.push({ moment: item.moment, events: item.events, lanes: item.lanes, column: item.column, slot, x, y: top, height: bottom - top, ghost })
    }
  }
  return { axis, columns, lanes, cards, moments, unplaced, unplacedMoments, width: HEADER_WIDTH + columns.length * COLUMN_WIDTH, height: y }
}

/** Return the integers from `start` to `end` inclusive. */
function range(start: number, end: number): number[] {
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
}

/** A shared moment as drawn: the lanes it touches, and the lanes it only passes through. */
export type Crossing = { momentId: number; column: number; lanes: number[]; passes: number[] }

/** List the crossings: each shared moment once, with its participant lanes and the lanes it spans past. */
export function crossings(layout: JourneyLayout): Crossing[] {
  return layout.moments.map(item => {
    const span = range(item.lanes[0], item.lanes[item.lanes.length - 1])
    return { momentId: item.moment.id, column: item.column, lanes: item.lanes, passes: span.filter(lane => !item.lanes.includes(lane)) }
  })
}

/** Cards in different lanes that share a scene or beat but no moment: candidates the writer may merge. */
export type MergeCandidate = { key: string; label: string; eventIds: number[] }

/** Find merge candidates (never merged automatically: the writer decides). */
export function mergeCandidates(events: TimelineEvent[], scenes: SceneLite[], beats: Beat[]): MergeCandidate[] {
  const groups = new Map<string, TimelineEvent[]>()
  for (const event of events) {
    if (event.moment_id !== null) continue
    const key = event.scene_id !== null ? `scene-${event.scene_id}` : event.beat_id !== null ? `beat-${event.beat_id}` : null
    if (key) groups.set(key, [...(groups.get(key) ?? []), event])
  }
  const sceneName = new Map(scenes.map(scene => [`scene-${scene.id}`, scene.heading]))
  const beatName = new Map(beats.map(beat => [`beat-${beat.id}`, beat.title]))
  return [...groups.entries()]
    .filter(([, rows]) => new Set(rows.map(row => row.character_id)).size > 1)
    .map(([key, rows]) => ({ key, label: sceneName.get(key) ?? beatName.get(key) ?? key, eventIds: rows.map(row => row.id) }))
}

/** The intensity band a card shows: deep low, low, even, high, peak. */
export function intensityBand(intensity: number): 'deep-low' | 'low' | 'even' | 'high' | 'peak' {
  if (intensity <= -3) return 'deep-low'
  if (intensity < 0) return 'low'
  if (intensity === 0) return 'even'
  return intensity >= 3 ? 'peak' : 'high'
}

export type CurvePoint = { column: number; x: number; value: number }

/** One lane's intensity across the axis: a point per column it appears in (several cards average). */
export function laneCurve(layout: JourneyLayout, lane: number): CurvePoint[] {
  const laneId = layout.lanes[lane]?.character.id
  const values = new Map<number, number[]>()
  const add = (column: number, value: number): void => { values.set(column, [...(values.get(column) ?? []), value]) }
  for (const card of layout.cards) if (card.lane === lane) add(card.column, card.event.intensity)
  for (const item of layout.moments) for (const event of item.events) if (event.character_id === laneId) add(item.column, event.intensity)
  return [...values.entries()].sort(([a], [b]) => a - b).map(([column, list]) => ({ column, x: layout.columns[column].x + COLUMN_WIDTH / 2, value: mean(list) }))
}

/** The cast overlay: per column, the average of the lanes that appear in it. */
export function castCurve(layout: JourneyLayout): CurvePoint[] {
  const perColumn = new Map<number, number[]>()
  layout.lanes.forEach(lane => {
    for (const point of laneCurve(layout, lane.index)) perColumn.set(point.column, [...(perColumn.get(point.column) ?? []), point.value])
  })
  return [...perColumn.entries()].sort(([a], [b]) => a - b).map(([column, list]) => ({ column, x: layout.columns[column].x + COLUMN_WIDTH / 2, value: mean(list) }))
}

/** Return the arithmetic mean (0 for none). */
function mean(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

/** Map an intensity (−5…+5) to a y within a band: +5 at the top, −5 at the bottom. */
export function curveY(value: number, top: number, height: number): number {
  const clamped = Math.max(-5, Math.min(5, value))
  return top + ((5 - clamped) / 10) * height
}

/** Build an SVG path through the points (empty for none; a single point is a short tick). */
export function curvePath(points: CurvePoint[], top: number, height: number): string {
  if (!points.length) return ''
  const coords = points.map(point => `${round(point.x)} ${round(curveY(point.value, top, height))}`)
  if (coords.length === 1) return `M ${round(points[0].x - 6)} ${coords[0].split(' ')[1]} L ${round(points[0].x + 6)} ${coords[0].split(' ')[1]}`
  return `M ${coords.join(' L ')}`
}

/** Round to one decimal for compact paths. */
function round(value: number): number {
  return Math.round(value * 10) / 10
}

// Reordering ---------------------------------------------------------------------------------------

/**
 * Move a scene `delta` places within its act (a reorder proposal can't move a scene between acts).
 * Return the new order, or null when the scene can't move that way.
 */
export function moveSceneInAct(order: number[], sceneId: number, delta: -1 | 1, actOf: Map<number, number>): number[] | null {
  const index = order.indexOf(sceneId)
  const target = index + delta
  if (index < 0 || target < 0 || target >= order.length || actOf.get(order[target]) !== actOf.get(sceneId)) return null
  const next = [...order]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

/** Move a scene to where `targetSceneId` is, clamped to the scene's own act. Null when nothing changes. */
export function moveSceneTo(order: number[], sceneId: number, targetSceneId: number, actOf: Map<number, number>): number[] | null {
  const act = actOf.get(sceneId)
  const inAct = order.filter(id => actOf.get(id) === act)
  const targetIndex = order.indexOf(targetSceneId)
  let target = targetSceneId
  if (actOf.get(targetSceneId) !== act) target = targetIndex < order.indexOf(inAct[0]) ? inAct[0] : inAct[inAct.length - 1]
  if (target === sceneId) return null
  const next = order.filter(id => id !== sceneId)
  const at = next.indexOf(target)
  const forward = order.indexOf(sceneId) < order.indexOf(target)
  next.splice(forward ? at + 1 : at, 0, sceneId)
  return next
}

/** The column index under a canvas x position (clamped to the columns). */
export function columnAt(layout: JourneyLayout, x: number): number {
  if (!layout.columns.length) return -1
  const index = Math.round((x - HEADER_WIDTH - (COLUMN_WIDTH - CARD_WIDTH) / 2) / COLUMN_WIDTH)
  return Math.max(0, Math.min(layout.columns.length - 1, index))
}

/** A story-world position that puts an item at `index` among `others` (sorted, distinct values). */
export function chronoAt(others: number[], index: number): number {
  if (!others.length) return 1
  if (index <= 0) return others[0] - 1
  if (index >= others.length) return others[others.length - 1] + 1
  return (others[index - 1] + others[index]) / 2
}

/** Move an item one story-world step earlier or later: past the neighbouring column. Null at the ends. */
export function stepChrono(values: number[], current: number | null, delta: -1 | 1): number | null {
  const others = [...new Set(values)].sort((a, b) => a - b)
  if (current === null) return delta > 0 ? chronoAt(others, others.length) : chronoAt(others, 0)
  const shares = others.includes(current)
  const before = others.filter(value => value < current)
  const after = others.filter(value => value > current)
  if (delta < 0) {
    if (shares) return chronoAt(others, before.length)
    return before.length ? chronoAt(others, before.length - 1) : null
  }
  if (shares) return chronoAt(others, before.length + 1)
  return after.length ? chronoAt(others, before.length + 1) : null
}
