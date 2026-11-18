import { describe, expect, it } from 'vitest'
import type { Beat, Character, StoryMoment, TimelineEvent } from '../storyApi'
import {
  castCurve, chronoAt, columnAt, COLUMN_WIDTH, crossings, curvePath, curveY, HEADER_WIDTH, intensityBand, type JourneyData,
  laneCurve, layoutJourney, mergeCandidates, moveSceneInAct, moveSceneTo, orderedCast, scriptOrder, SLOT_HEIGHT, stepChrono,
} from './layout'

const character = (id: number, name: string, position: number): Character => ({
  id, project_id: 1, version: 1, position, name, role: '', summary: '', bio: '', want: '', need: '', motive: '', objective: '', flaw: '',
  arc_summary: '', voice: '', notes: '', aliases: [], tags: [], cue: null, dialogue_lines: 0, scene_ids: [], source: 'writer', writer_edited: false,
})
const event = (id: number, characterId: number, fields: Partial<TimelineEvent> = {}): TimelineEvent => ({
  id, project_id: 1, version: 1, character_id: characterId, position: id, story_time: '', title: `Event ${id}`, description: '', objective: '',
  emotional_state: '', motivation: '', history: '', intensity: 0, chrono_index: null, scene_id: null, beat_id: null, moment_id: null, ...fields,
})
const moment = (id: number, fields: Partial<StoryMoment> = {}): StoryMoment => ({
  id, project_id: 1, version: 1, title: `Moment ${id}`, summary: '', chrono_index: null, story_time: '', scene_id: null, beat_id: null, ...fields,
})
const beat = (id: number, actId: number | null, position: number, sceneIds: number[] = []): Beat => ({
  id, project_id: 1, version: 1, act_id: actId, position, title: `Beat ${id}`, summary: '', beat_type: 'beat', status: 'planned', scene_ids: sceneIds, character_ids: [], source: 'writer',
})

const acts = [{ id: 1, screenplay_id: 9, title: 'Act One', position: 0 }, { id: 2, screenplay_id: 9, title: 'Act Two', position: 1 }]
const scenes = [
  { id: 10, act_id: 1, heading: 'INT. RIVER', position: 0 },
  { id: 11, act_id: 1, heading: 'EXT. TOWN', position: 1 },
  { id: 20, act_id: 2, heading: 'INT. HOSPITAL', position: 0 },
]
const cast = [character(1, 'Will', 1), character(2, 'Edward', 0), character(3, 'Sandra', 2)]

/** Build journey data with the shared defaults. */
function data(fields: Partial<JourneyData>): JourneyData {
  return { characters: cast, events: [], moments: [], acts, scenes, beats: [], ...fields }
}

describe('lane layout', () => {
  it('orders lanes by the cast order, or by a local lane order', () => {
    expect(orderedCast(cast).map(row => row.name)).toEqual(['Edward', 'Will', 'Sandra'])
    expect(orderedCast(cast, [3, 1]).map(row => row.name)).toEqual(['Sandra', 'Will', 'Edward'])
    const layout = layoutJourney(data({}), 'narrative')
    expect(layout.lanes.map(lane => lane.character.name)).toEqual(['Edward', 'Will', 'Sandra'])
    expect(layout.lanes[1].y).toBe(layout.lanes[0].y + layout.lanes[0].height)
  })

  it('builds narrative columns per act: scenes in script order, then beats that link no scene', () => {
    const layout = layoutJourney(data({ beats: [beat(5, 1, 0, [11]), beat(6, 2, 1), beat(7, null, 0)] }), 'narrative')
    expect(layout.columns.map(column => column.key)).toEqual(['scene-10', 'scene-11', 'scene-20', 'beat-6', 'beat-7'])
    expect(layout.columns[0].x).toBe(HEADER_WIDTH)
    expect(layout.columns[1].x).toBe(HEADER_WIDTH + COLUMN_WIDTH)
  })

  it('places cards by scene, beat or linked beat, and sends the rest to the Unplaced tray', () => {
    const layout = layoutJourney(data({
      beats: [beat(5, 1, 0, [11]), beat(6, 2, 0)],
      events: [event(1, 1, { scene_id: 20 }), event(2, 2, { beat_id: 5 }), event(3, 3, { beat_id: 6 }), event(4, 3)],
    }), 'narrative')
    const columnOf = (id: number) => layout.columns[layout.cards.find(card => card.event.id === id)!.column].key
    expect(columnOf(1)).toBe('scene-20')
    expect(columnOf(2)).toBe('scene-11')
    expect(columnOf(3)).toBe('beat-6')
    expect(layout.unplaced.map(row => row.id)).toEqual([4])
    expect(layout.cards.find(card => card.event.id === 1)!.lane).toBe(1)
  })

  it('stacks cards that share a cell and grows the lane', () => {
    const layout = layoutJourney(data({ events: [event(1, 2, { scene_id: 10 }), event(2, 2, { scene_id: 10 })] }), 'narrative')
    expect(layout.cards.map(card => card.slot)).toEqual([0, 1])
    expect(layout.lanes[0].height).toBeGreaterThan(layout.lanes[1].height)
    expect(layout.cards[1].y - layout.cards[0].y).toBe(SLOT_HEIGHT)
  })

  it('lays the chronology axis out by chrono_index, labelled by story time, undated cards unplaced', () => {
    const layout = layoutJourney(data({
      events: [event(1, 1, { chrono_index: 3, story_time: '1973' }), event(2, 2, { chrono_index: 1, story_time: 'Childhood' }), event(3, 3, { chrono_index: 3 }), event(4, 3)],
    }), 'chronology')
    expect(layout.columns.map(column => column.label)).toEqual(['Childhood', '1973'])
    expect(layout.cards.filter(card => card.column === 1).map(card => card.event.id).sort()).toEqual([1, 3])
    expect(layout.unplaced.map(row => row.id)).toEqual([4])
  })

  it('marks moved scenes in a proposed order as ghosts', () => {
    const layout = layoutJourney(data({ events: [event(1, 1, { scene_id: 11 }), event(2, 2, { scene_id: 20 })] }), 'narrative', { order: [11, 10, 20] })
    expect(layout.columns[0]).toMatchObject({ sceneId: 11, movedFrom: 2, label: '1. EXT. TOWN' })
    expect(layout.cards.find(card => card.event.id === 1)!.ghost).toBe(true)
    expect(layout.cards.find(card => card.event.id === 2)!.ghost).toBe(false)
  })
})

describe('crossings', () => {
  const shared = data({
    moments: [moment(50, { scene_id: 20, chrono_index: 2 }), moment(51)],
    events: [
      event(1, 2, { moment_id: 50, intensity: -4 }), event(2, 3, { moment_id: 50, intensity: 2 }),
      event(3, 1, { scene_id: 20 }), event(4, 1, { moment_id: 99, scene_id: 10 }),
    ],
  })

  it('draws a shared moment once across the lanes of everyone in it', () => {
    const layout = layoutJourney(shared, 'narrative')
    expect(layout.moments).toHaveLength(1)
    expect(layout.moments[0].lanes).toEqual([0, 2])
    expect(crossings(layout)).toEqual([{ momentId: 50, column: 2, lanes: [0, 2], passes: [1] }])
    // The lane it passes through stacks its own card below the moment's slot.
    expect(layout.cards.find(card => card.event.id === 3)!.slot).toBe(1)
    // An event pointing at a missing moment is a plain card; a moment nobody joined waits in the tray.
    expect(layout.cards.find(card => card.event.id === 4)!.column).toBe(0)
    expect(layout.unplacedMoments.map(row => row.id)).toEqual([51])
    expect(layout.moments[0].height).toBeGreaterThan(SLOT_HEIGHT * 2)
  })

  it('places a moment on the chronology axis by its own chrono_index', () => {
    const layout = layoutJourney(shared, 'chronology')
    expect(layout.moments[0].column).toBe(0)
    expect(layout.columns[0].chrono).toBe(2)
  })

  it('offers merge candidates for cards in different lanes sharing a scene, never inside a moment', () => {
    const rows = [event(1, 1, { scene_id: 10 }), event(2, 2, { scene_id: 10 }), event(3, 2, { scene_id: 11 }), event(4, 3, { scene_id: 11 }), event(5, 3, { scene_id: 11, moment_id: 7 }), event(6, 1, { beat_id: 5 }), event(7, 1, { beat_id: 5 })]
    expect(mergeCandidates(rows, scenes, [beat(5, 1, 0)])).toEqual([
      { key: 'scene-10', label: 'INT. RIVER', eventIds: [1, 2] },
      { key: 'scene-11', label: 'EXT. TOWN', eventIds: [3, 4] },
    ])
  })
})

describe('keyboard reorder', () => {
  const order = scriptOrder(acts, scenes)
  const actOf = new Map(scenes.map(scene => [scene.id, scene.act_id]))

  it('reads the script order across acts', () => {
    expect(order).toEqual([10, 11, 20])
  })

  it('moves a scene earlier or later within its act only', () => {
    expect(moveSceneInAct(order, 11, -1, actOf)).toEqual([11, 10, 20])
    expect(moveSceneInAct(order, 10, -1, actOf)).toBeNull()
    expect(moveSceneInAct(order, 11, 1, actOf)).toBeNull()
    expect(moveSceneInAct(order, 20, 1, actOf)).toBeNull()
  })

  it('drops a scene onto another, clamped to its act', () => {
    expect(moveSceneTo(order, 11, 10, actOf)).toEqual([11, 10, 20])
    expect(moveSceneTo(order, 10, 11, actOf)).toEqual([11, 10, 20])
    expect(moveSceneTo(order, 10, 20, actOf)).toEqual([11, 10, 20])
    expect(moveSceneTo(order, 20, 10, actOf)).toBeNull()
  })

  it('maps a canvas x back to a column', () => {
    const layout = layoutJourney(data({}), 'narrative')
    expect(columnAt(layout, HEADER_WIDTH + 12)).toBe(0)
    expect(columnAt(layout, HEADER_WIDTH + COLUMN_WIDTH * 1.4)).toBe(1)
    expect(columnAt(layout, -500)).toBe(0)
    expect(columnAt(layout, 99_999)).toBe(2)
  })

  it('steps a card through story-world time past its neighbours', () => {
    expect(chronoAt([], 0)).toBe(1)
    expect(chronoAt([1, 3], 1)).toBe(2)
    expect(stepChrono([1, 2, 4], 3, -1)).toBe(1.5)
    expect(stepChrono([1, 2, 4], 3, 1)).toBe(5)
    expect(stepChrono([2, 4], 1, -1)).toBeNull()
    expect(stepChrono([2, 4], 5, 1)).toBeNull()
    // Sharing a column: a step leaves it on that side.
    expect(stepChrono([1, 2, 4], 2, -1)).toBe(1.5)
    expect(stepChrono([1, 2, 4], 2, 1)).toBe(3)
    // Undated: a step places it at an end.
    expect(stepChrono([1, 2], null, 1)).toBe(3)
  })
})

describe('intensity curve', () => {
  const layout = layoutJourney(data({
    moments: [moment(50, { scene_id: 11 })],
    events: [
      event(1, 2, { scene_id: 10, intensity: 4 }), event(2, 2, { scene_id: 10, intensity: 2 }),
      event(3, 2, { moment_id: 50, intensity: -5 }), event(4, 1, { moment_id: 50, intensity: 1 }), event(5, 1, { scene_id: 20, intensity: -2 }),
    ],
  }), 'narrative')

  it('draws a lane point per column, averaging stacked cards and counting moment sides', () => {
    expect(laneCurve(layout, 0).map(point => [point.column, point.value])).toEqual([[0, 3], [1, -5]])
    expect(laneCurve(layout, 1).map(point => [point.column, point.value])).toEqual([[1, 1], [2, -2]])
    expect(laneCurve(layout, 2)).toEqual([])
    expect(laneCurve(layout, 0)[0].x).toBe(HEADER_WIDTH + COLUMN_WIDTH / 2)
  })

  it('averages the lanes for the cast overlay', () => {
    expect(castCurve(layout).map(point => [point.column, point.value])).toEqual([[0, 3], [1, -2], [2, -2]])
  })

  it('maps −5…+5 into the band and builds the path', () => {
    expect(curveY(5, 100, 80)).toBe(100)
    expect(curveY(-5, 100, 80)).toBe(180)
    expect(curveY(0, 100, 80)).toBe(140)
    expect(curveY(9, 100, 80)).toBe(100)
    expect(curvePath([], 0, 10)).toBe('')
    expect(curvePath([{ column: 0, x: 10, value: 5 }, { column: 1, x: 30, value: -5 }], 0, 10)).toBe('M 10 0 L 30 10')
    expect(curvePath([{ column: 0, x: 10, value: 0 }], 0, 10)).toBe('M 4 5 L 16 5')
  })

  it('bands intensity for the card colour', () => {
    expect([-5, -1, 0, 2, 3].map(intensityBand)).toEqual(['deep-low', 'low', 'even', 'high', 'peak'])
  })
})
