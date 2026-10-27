import type { StoryVisuals, VisualScene } from '../storyApi'
import { workspace } from '../test/harness'

/** A visual scene row for tests. */
export const scene = (id: number, actId: number, index: number, heading: string, intensity: number | null, runtime = 60, extra: Partial<VisualScene> = {}): VisualScene => ({
  id, act_id: actId, index, heading, runtime_seconds: runtime, start_seconds: index * 60, intensity, event_count: intensity === null ? 0 : 2, character_ids: [], ...extra,
})

/** A small two-act draft: a rising first act, a dip in the second, and two milestones. */
export function sampleVisuals(extra: Partial<StoryVisuals> = {}): StoryVisuals {
  return {
    screenplay_id: 12,
    total_runtime_seconds: 300,
    acts: [{ id: 4, title: 'Act One', position: 0 }, { id: 5, title: 'Act Two', position: 1 }],
    scenes: [
      scene(21, 4, 0, 'EXT. RIVER - DAY', 1),
      scene(22, 4, 1, 'INT. CIRCUS - NIGHT', 4, 120),
      scene(23, 5, 2, 'EXT. WAR - DAY', null),
      scene(24, 5, 3, 'INT. HOSPITAL - NIGHT', -3, 60),
    ].map((row, index, rows) => ({ ...row, start_seconds: rows.slice(0, index).reduce((sum, item) => sum + item.runtime_seconds, 0) })),
    milestones: [
      { beat_id: 1, title: 'Meets Sandra', beat_type: 'inciting_incident', act_id: 4, scene_id: 22, scene_index: 1 },
      { beat_id: 2, title: 'The end', beat_type: 'climax', act_id: 5, scene_id: null, scene_index: null },
    ],
    characters: [
      { id: 7, name: 'Edward', role: 'lead', moment_count: 3 },
      { id: 8, name: 'Will', role: '', moment_count: 1 },
      { id: 9, name: 'Sandra', role: '', moment_count: 2 },
    ],
    edges: [
      { source: 7, target: 8, shared_moments: 1, shared_scenes: 2, relations: ['son'] },
      { source: 7, target: 9, shared_moments: 2, shared_scenes: 1, relations: [] },
      { source: 8, target: 9, shared_moments: 0, shared_scenes: 0, relations: ['in-law'] },
    ],
    ...extra,
  }
}

/** Mocks every request the project shell and the visual tools make. */
export function visualsRoutes(visuals: StoryVisuals, beats: unknown[] = []) {
  return {
    'GET /api/v1/projects/3/workspace': workspace(3, { acts: [{ id: 4, screenplay_id: 12, title: 'Act One', position: 0 }, { id: 5, screenplay_id: 12, title: 'Act Two', position: 1 }] }),
    'GET /api/v1/projects/3/storyline': { project_id: 3, version: 1, title: 'Lantern House' },
    'GET /api/v1/projects/3/characters': [],
    'GET /api/v1/projects/3/beats': () => beats,
    'GET /api/v1/projects/3/visuals': () => visuals,
  }
}
