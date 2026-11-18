import type { Character, StoryMoment, TimelineEvent } from '../storyApi'
import type { Target } from './JourneyCanvas'

/** What the chat sees of the Journey map: the selected card, moment or lane, and its scene. */
export type JourneyFocus = { selection: string | null; sceneId: number | null }

type FocusData = { characters: Character[]; events: TimelineEvent[]; moments: StoryMoment[] }

const signed = (value: number) => (value > 0 ? `+${value}` : String(value))

/** Describe the selected card or moment (else the selected lane) with the ids the room's tools take. */
export function journeyFocus(data: FocusData, selected: Target | null, laneId: number | null): JourneyFocus {
  const name = (id: number) => data.characters.find(row => row.id === id)?.name ?? `character #${id}`
  if (selected?.kind === 'event') {
    const event = data.events.find(row => row.id === selected.id)
    if (event) {
      const facts = [`intensity ${signed(event.intensity)}`]
      if (event.story_time) facts.push(`story time ${event.story_time}`)
      if (event.scene_id !== null) facts.push(`scene #${event.scene_id}`)
      if (event.moment_id !== null) facts.push(`shared moment #${event.moment_id}`)
      if (event.motivation) facts.push(`motivation: ${event.motivation.slice(0, 120)}`)
      return { selection: `Card #${event.id} “${event.title}” in ${name(event.character_id)}’s lane (${facts.join(', ')})`, sceneId: event.scene_id }
    }
  }
  if (selected?.kind === 'moment') {
    const moment = data.moments.find(row => row.id === selected.id)
    if (moment) {
      const sides = data.events.filter(row => row.moment_id === moment.id)
      const who = sides.map(row => `${name(row.character_id)} (card #${row.id})`).join(', ') || 'nobody yet'
      return { selection: `Shared moment #${moment.id} “${moment.title}” with ${who}${moment.scene_id !== null ? `, scene #${moment.scene_id}` : ''}`, sceneId: moment.scene_id }
    }
  }
  if (laneId !== null) {
    const character = data.characters.find(row => row.id === laneId)
    if (character) {
      const cards = data.events.filter(row => row.character_id === laneId).length
      return { selection: `Lane: ${character.name} (character #${character.id}${character.role ? `, ${character.role}` : ''}), ${cards} card${cards === 1 ? '' : 's'}`, sceneId: null }
    }
  }
  return { selection: null, sceneId: null }
}
