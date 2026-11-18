import { describe, expect, it } from 'vitest'
import type { Character, StoryMoment, TimelineEvent } from '../storyApi'
import { journeyFocus } from './focus'

const character = (id: number, name: string, role = ''): Character => ({ id, name, role } as Character)
const event = (id: number, characterId: number, fields: Partial<TimelineEvent> = {}): TimelineEvent => ({
  id, character_id: characterId, title: `Card ${id}`, intensity: 0, story_time: '', motivation: '', scene_id: null, moment_id: null, ...fields,
} as TimelineEvent)
const data = {
  characters: [character(1, 'Edward', 'protagonist'), character(2, 'Will')],
  events: [event(10, 1, { intensity: -3, story_time: '1937', scene_id: 4, moment_id: 7, motivation: 'Fear' }), event(11, 2, { moment_id: 7 })],
  moments: [{ id: 7, title: 'The river', scene_id: 4 } as StoryMoment],
}

describe('journey chat focus', () => {
  it('describes a selected card with the ids the room needs', () => {
    expect(journeyFocus(data, { kind: 'event', id: 10 }, null)).toEqual({
      selection: 'Card #10 “Card 10” in Edward’s lane (intensity -3, story time 1937, scene #4, shared moment #7, motivation: Fear)', sceneId: 4,
    })
  })

  it('describes a shared moment and its sides', () => {
    expect(journeyFocus(data, { kind: 'moment', id: 7 }, 2).selection).toBe('Shared moment #7 “The river” with Edward (card #10), Will (card #11), scene #4')
  })

  it('falls back to the selected lane, then to nothing', () => {
    expect(journeyFocus(data, null, 1)).toEqual({ selection: 'Lane: Edward (character #1, protagonist), 1 card', sceneId: null })
    expect(journeyFocus(data, null, null)).toEqual({ selection: null, sceneId: null })
  })
})
