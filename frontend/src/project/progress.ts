import type { ProjectWorkspace } from '../api'
import type { Beat, Character, Storyline } from '../storyApi'

export type StageKey = 'storyline' | 'characters' | 'outline' | 'script'
export type StageState = 'empty' | 'started' | 'done'
export type Gap = { label: string; to: string }
export type Stage = { key: StageKey; label: string; to: string; state: StageState; summary: string; gaps: Gap[] }

export type ProgressInput = {
  projectId: number
  storyline?: Storyline
  characters?: Character[]
  beats?: Beat[]
  workspace?: ProjectWorkspace
}

export const STORYLINE_FIELDS = [
  { name: 'logline', label: 'Logline' },
  { name: 'premise', label: 'Premise' },
  { name: 'synopsis', label: 'Synopsis' },
  { name: 'theme', label: 'Theme' },
  { name: 'tone', label: 'Tone' },
] as const

/** Character fields the room leans on most; an empty one is a gap. */
export const CHARACTER_CORE_FIELDS = [
  { name: 'motive', label: 'motive' },
  { name: 'objective', label: 'objective' },
  { name: 'want', label: 'want' },
  { name: 'need', label: 'need' },
  { name: 'arc_summary', label: 'arc' },
] as const

const filled = (value: string | null | undefined): boolean => Boolean(value && value.trim())

function stateOf(done: number, total: number): StageState {
  if (total > 0 && done === total) return 'done'
  return done > 0 ? 'started' : 'empty'
}

function storylineStage({ projectId, storyline }: ProgressInput): Stage {
  const to = `/projects/${projectId}/storyline`
  const missing = STORYLINE_FIELDS.filter(field => !filled(storyline?.[field.name]))
  const done = STORYLINE_FIELDS.length - missing.length
  const summary = storyline ? `${filled(storyline.logline) ? 'Logline set' : 'No logline'} · ${done}/${STORYLINE_FIELDS.length}` : '—'
  return {
    key: 'storyline', label: 'Storyline', to, summary,
    state: storyline ? stateOf(done, STORYLINE_FIELDS.length) : 'empty',
    gaps: storyline ? missing.map(field => ({ label: `${field.label} is empty`, to: `${to}?field=${field.name}` })) : [],
  }
}

function charactersStage({ projectId, characters }: ProgressInput): Stage {
  const to = `/projects/${projectId}/characters`
  const cast = characters ?? []
  const grounded = cast.filter(row => filled(row.motive) && filled(row.objective))
  const gaps: Gap[] = cast.length === 0 ? [{ label: 'No characters yet', to }] : []
  for (const row of cast) {
    const empty = CHARACTER_CORE_FIELDS.filter(field => !filled(row[field.name]))
    if (empty.length) gaps.push({ label: `${row.name}: no ${empty.map(field => field.label).join(', ')}`, to: `${to}/${row.id}?field=${empty[0].name}` })
  }
  return {
    key: 'characters', label: 'Characters', to, gaps,
    state: cast.length === 0 ? 'empty' : grounded.length === cast.length ? 'done' : 'started',
    summary: characters ? `${cast.length} · ${grounded.length} with motive & objective` : '—',
  }
}

function outlineStage({ projectId, beats, workspace }: ProgressInput): Stage {
  const to = `/projects/${projectId}/outline`
  const list = beats ?? []
  const linked = list.filter(beat => beat.scene_ids.length > 0)
  const gaps: Gap[] = list.length === 0 ? [{ label: 'No beats yet', to }] : []
  for (const act of workspace?.acts ?? []) {
    if (!list.some(beat => beat.act_id === act.id)) gaps.push({ label: `${act.title || `Act ${act.position + 1}`} has no beats`, to })
  }
  for (const beat of list) if (beat.scene_ids.length === 0) gaps.push({ label: `Beat “${beat.title}” has no scene`, to })
  return {
    key: 'outline', label: 'Outline', to, gaps,
    state: list.length === 0 ? 'empty' : linked.length === list.length ? 'done' : 'started',
    summary: beats ? `${list.length} beats · ${linked.length} linked` : '—',
  }
}

function scriptStage({ projectId, workspace }: ProgressInput): Stage {
  const to = `/projects/${projectId}`
  const scenes = workspace?.scenes ?? []
  const written = scenes.filter(scene => (workspace?.blocks[scene.id]?.length ?? 0) > 0 || filled(scene.body))
  const gaps: Gap[] = scenes.length === 0 ? [{ label: 'No scenes yet', to }] : []
  for (const scene of scenes) if (!written.includes(scene)) gaps.push({ label: `${scene.heading} is empty`, to: `${to}?scene=${scene.id}` })
  return {
    key: 'script', label: 'Script', to, gaps,
    state: scenes.length === 0 ? 'empty' : written.length === scenes.length ? 'done' : 'started',
    summary: workspace ? `${scenes.length} scenes` : '—',
  }
}

/** Summarise each step of the manual flow: Storyline → Characters → Outline → Script. */
export function projectStages(input: ProgressInput): Stage[] {
  return [storylineStage(input), charactersStage(input), outlineStage(input), scriptStage(input)]
}
