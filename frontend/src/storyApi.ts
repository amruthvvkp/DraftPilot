import { request } from './api'

/** Who created a story row: the writer, the Twin Keeper (derived from the draft), an approved agent proposal, or an import. */
export type EntitySource = 'writer' | 'twin' | 'agent' | 'import'

export type Character = {
  id: number; project_id: number; version: number; position: number
  name: string; role: string; summary: string; bio: string
  want: string; need: string; motive: string; objective: string; flaw: string; arc_summary: string; voice: string; notes: string
  aliases: string[]; tags: string[]
  cue: string | null; dialogue_lines: number; scene_ids: number[]; source: EntitySource; writer_edited: boolean
}
export type CharacterFields = Partial<Omit<Character, 'id' | 'project_id' | 'version' | 'dialogue_lines' | 'scene_ids' | 'source' | 'writer_edited'>>

export type TimelineEvent = {
  id: number; project_id: number; version: number; character_id: number; position: number
  story_time: string; title: string; description: string; objective: string; emotional_state: string
  motivation: string; history: string
  /** Emotional valence, −5 (a low) … +5 (a high). */
  intensity: number
  /** Sortable story-world position; `story_time` is its label. Null means undated. */
  chrono_index: number | null
  scene_id: number | null; beat_id: number | null; moment_id: number | null
}
export type TimelineEventFields = Partial<Omit<TimelineEvent, 'id' | 'project_id' | 'version'>>

/** A moment several characters share; each participant's event links to it with `moment_id`. */
export type StoryMoment = {
  id: number; project_id: number; version: number
  title: string; summary: string; chrono_index: number | null; story_time: string; scene_id: number | null; beat_id: number | null
}
export type StoryMomentFields = Partial<Omit<StoryMoment, 'id' | 'project_id' | 'version'>>

/** A named narrative order (scene ids in telling order) saved without applying it. */
export type NarrativeVariant = { id: number; project_id: number; version: number; name: string; scene_ids: number[] }

export type Relationship = { id: number; project_id: number; version: number; source_character_id: number; target_character_id: number; relation: string; description: string }

export type Location = {
  id: number; project_id: number; version: number; position: number
  name: string; description: string; visual_notes: string; notes: string
  heading_location: string | null; int_ext: string[]; times: string[]; scene_ids: number[]; source: EntitySource; writer_edited: boolean
}
export type LocationFields = Partial<Pick<Location, 'name' | 'description' | 'visual_notes' | 'notes' | 'position'>>

export type Beat = {
  id: number; project_id: number; version: number; act_id: number | null; position: number
  title: string; summary: string; beat_type: string; status: string; scene_ids: number[]; character_ids: number[]; source: EntitySource
}
export type BeatFields = Partial<Omit<Beat, 'id' | 'project_id' | 'version' | 'source'>>

export type Storyline = {
  project_id: number; version: number
  title: string; logline: string | null; premise: string | null; synopsis: string | null; theme: string | null; tone: string | null
  description: string | null; story_outline: string | null
}
export type StorylineFields = Partial<Omit<Storyline, 'project_id' | 'version'>>

export type Act = { id: number; screenplay_id: number; title: string | null; position: number }

const base = (projectId: number) => `/api/v1/projects/${projectId}`
const versioned = (version: number) => ({ 'If-Match': String(version) })

type Collection = 'characters' | 'timeline-events' | 'relationships' | 'locations' | 'beats' | 'moments' | 'narrative-variants'

function list<T>(projectId: number, collection: Collection, query = ''): Promise<T[]> {
  return request<T[]>(`${base(projectId)}/${collection}${query}`)
}
function create<T>(projectId: number, collection: Collection, fields: object): Promise<T> {
  return request<T>(`${base(projectId)}/${collection}`, { method: 'POST', body: JSON.stringify(fields) })
}
function update<T>(projectId: number, collection: Collection, id: number, version: number, fields: object): Promise<T> {
  return request<T>(`${base(projectId)}/${collection}/${id}`, { method: 'PATCH', headers: versioned(version), body: JSON.stringify(fields) })
}
function remove(projectId: number, collection: Collection, id: number, version: number): Promise<void> {
  return request<void>(`${base(projectId)}/${collection}/${id}`, { method: 'DELETE', headers: versioned(version) })
}

export const storyApi = {
  storyline: (projectId: number) => request<Storyline>(`${base(projectId)}/storyline`),
  updateStoryline: (projectId: number, version: number, fields: StorylineFields) =>
    request<Storyline>(base(projectId), { method: 'PATCH', headers: versioned(version), body: JSON.stringify(fields) }),

  characters: (projectId: number) => list<Character>(projectId, 'characters'),
  createCharacter: (projectId: number, fields: CharacterFields & { name: string }) => create<Character>(projectId, 'characters', fields),
  updateCharacter: (projectId: number, row: Character, fields: CharacterFields) => update<Character>(projectId, 'characters', row.id, row.version, fields),
  deleteCharacter: (projectId: number, row: Character) => remove(projectId, 'characters', row.id, row.version),

  timeline: (projectId: number, characterId?: number) =>
    list<TimelineEvent>(projectId, 'timeline-events', characterId ? `?character_id=${characterId}` : ''),
  createEvent: (projectId: number, fields: TimelineEventFields & { character_id: number; title: string }) => create<TimelineEvent>(projectId, 'timeline-events', fields),
  updateEvent: (projectId: number, row: TimelineEvent, fields: TimelineEventFields) => update<TimelineEvent>(projectId, 'timeline-events', row.id, row.version, fields),
  deleteEvent: (projectId: number, row: TimelineEvent) => remove(projectId, 'timeline-events', row.id, row.version),

  relationships: (projectId: number) => list<Relationship>(projectId, 'relationships'),
  createRelationship: (projectId: number, fields: Omit<Relationship, 'id' | 'project_id' | 'version'>) => create<Relationship>(projectId, 'relationships', fields),
  updateRelationship: (projectId: number, row: Relationship, fields: Partial<Pick<Relationship, 'relation' | 'description'>>) =>
    update<Relationship>(projectId, 'relationships', row.id, row.version, fields),
  deleteRelationship: (projectId: number, row: Relationship) => remove(projectId, 'relationships', row.id, row.version),

  locations: (projectId: number) => list<Location>(projectId, 'locations'),
  createLocation: (projectId: number, fields: LocationFields & { name: string }) => create<Location>(projectId, 'locations', fields),
  updateLocation: (projectId: number, row: Location, fields: LocationFields) => update<Location>(projectId, 'locations', row.id, row.version, fields),
  deleteLocation: (projectId: number, row: Location) => remove(projectId, 'locations', row.id, row.version),

  beats: (projectId: number) => list<Beat>(projectId, 'beats'),
  createBeat: (projectId: number, fields: BeatFields & { title: string }) => create<Beat>(projectId, 'beats', fields),
  updateBeat: (projectId: number, row: Beat, fields: BeatFields) => update<Beat>(projectId, 'beats', row.id, row.version, fields),
  deleteBeat: (projectId: number, row: Beat) => remove(projectId, 'beats', row.id, row.version),

  moments: (projectId: number) => list<StoryMoment>(projectId, 'moments'),
  createMoment: (projectId: number, fields: StoryMomentFields & { title: string }) => create<StoryMoment>(projectId, 'moments', fields),
  updateMoment: (projectId: number, row: StoryMoment, fields: StoryMomentFields) => update<StoryMoment>(projectId, 'moments', row.id, row.version, fields),
  deleteMoment: (projectId: number, row: StoryMoment) => remove(projectId, 'moments', row.id, row.version),

  variants: (projectId: number) => list<NarrativeVariant>(projectId, 'narrative-variants'),
  createVariant: (projectId: number, fields: { name: string; scene_ids: number[] }) => create<NarrativeVariant>(projectId, 'narrative-variants', fields),
  deleteVariant: (projectId: number, row: NarrativeVariant) => remove(projectId, 'narrative-variants', row.id, row.version),

  createAct: (projectId: number, title: string, screenplayId?: number) =>
    request<Act>(`${base(projectId)}/acts`, { method: 'POST', body: JSON.stringify({ title, screenplay_id: screenplayId ?? null }) }),
  updateAct: (projectId: number, actId: number, fields: { title?: string; position?: number }) =>
    request<Act>(`${base(projectId)}/acts/${actId}`, { method: 'PATCH', body: JSON.stringify(fields) }),
  deleteAct: (projectId: number, actId: number, moveScenesTo?: number) =>
    request<void>(`${base(projectId)}/acts/${actId}${moveScenesTo ? `?move_scenes_to=${moveScenesTo}` : ''}`, { method: 'DELETE' }),

  createScene: (projectId: number, heading: string, options: { actId?: number; position?: number; screenplayId?: number } = {}) =>
    request<{ id: number; act_id: number; version: number; heading: string; position: number }>(`${base(projectId)}/scenes`, {
      method: 'POST',
      body: JSON.stringify({ heading, act_id: options.actId ?? null, position: options.position ?? null, screenplay_id: options.screenplayId ?? null }),
    }),
  moveScene: (projectId: number, sceneId: number, version: number, position: number, actId?: number) =>
    request<{ id: number; act_id: number; version: number }>(`${base(projectId)}/scenes/${sceneId}/move`, {
      method: 'POST', headers: versioned(version), body: JSON.stringify({ position, act_id: actId ?? null }),
    }),
  deleteScene: (projectId: number, sceneId: number, version: number) =>
    request<void>(`${base(projectId)}/scenes/${sceneId}`, { method: 'DELETE', headers: versioned(version) }),
}
