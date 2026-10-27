import { keepPreviousData, QueryClient, type QueryKey, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { ApiError, getProjectWorkspace, getStoryTwin, listArtifacts, listProjects, type ProjectEvent } from '../api'
import { storyApi } from '../storyApi'

/** Build the studio's query client: no retries on client errors, no refetch on focus (it would clobber typing). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: false,
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
      mutations: { retry: false },
    },
  })
}

/** Query keys. Everything about one project lives under `['project', id]`, so a prefix invalidates it all. */
export const keys = {
  projects: ['projects'] as const,
  project: (projectId: number) => ['project', projectId] as const,
  workspace: (projectId: number, draftId: number | null = null) => ['project', projectId, 'workspace', draftId] as const,
  workspaces: (projectId: number) => ['project', projectId, 'workspace'] as const,
  storyline: (projectId: number) => ['project', projectId, 'storyline'] as const,
  characters: (projectId: number) => ['project', projectId, 'characters'] as const,
  timeline: (projectId: number, characterId?: number) => ['project', projectId, 'timeline', characterId ?? 'all'] as const,
  timelines: (projectId: number) => ['project', projectId, 'timeline'] as const,
  relationships: (projectId: number) => ['project', projectId, 'relationships'] as const,
  locations: (projectId: number) => ['project', projectId, 'locations'] as const,
  beats: (projectId: number) => ['project', projectId, 'beats'] as const,
  twin: (projectId: number) => ['project', projectId, 'twin'] as const,
  artifacts: (projectId: number) => ['project', projectId, 'artifacts'] as const,
  proposals: (projectId: number) => ['project', projectId, 'proposals'] as const,
  runs: (projectId: number) => ['project', projectId, 'runs'] as const,
  run: (projectId: number, runId: number) => ['project', projectId, 'runs', runId] as const,
  threads: (projectId: number) => ['project', projectId, 'threads'] as const,
}

const STORY_KIND_KEYS: Record<string, (projectId: number) => QueryKey[]> = {
  character: id => [keys.characters(id), keys.relationships(id), keys.timelines(id), keys.beats(id), keys.twin(id)],
  timeline_event: id => [keys.timelines(id)],
  relationship: id => [keys.relationships(id)],
  location: id => [keys.locations(id), keys.twin(id)],
  beat: id => [keys.beats(id), keys.timelines(id)],
}

/** Return the query keys a live-sync event makes stale. */
export function staleKeysFor(projectId: number, event: Pick<ProjectEvent, 'kind' | 'data'>): QueryKey[] {
  switch (event.kind) {
    case 'scene.changed':
      return [keys.workspaces(projectId), keys.twin(projectId)]
    case 'structure.changed':
      return [keys.workspaces(projectId), keys.beats(projectId), keys.characters(projectId), keys.locations(projectId), keys.timelines(projectId)]
    case 'screenplay.changed':
    case 'timeline.changed':
    case 'translation.changed':
      return [keys.workspaces(projectId)]
    case 'story.changed': {
      const kind = typeof event.data?.kind === 'string' ? event.data.kind : ''
      return [...(STORY_KIND_KEYS[kind]?.(projectId) ?? [keys.project(projectId)]), keys.twin(projectId)]
    }
    case 'project.changed':
      return [keys.storyline(projectId), keys.workspaces(projectId), keys.twin(projectId), keys.projects]
    case 'twin.changed':
      return [keys.twin(projectId), keys.characters(projectId), keys.locations(projectId)]
    case 'artifact.changed':
      return [keys.artifacts(projectId)]
    case 'proposal.changed':
      return [keys.proposals(projectId)]
    case 'run.changed':
    case 'workflow.progress':
      return [keys.runs(projectId)]
    default:
      return []
  }
}

/** Mark every query an event touches as stale (active ones refetch). */
export function invalidateForEvent(client: QueryClient, projectId: number, event: Pick<ProjectEvent, 'kind' | 'data'>): void {
  for (const queryKey of staleKeysFor(projectId, event)) void client.invalidateQueries({ queryKey })
}

/** The draft chosen in the URL (`?draft=<screenplay id>`), or null for the project's first draft. */
export function useDraftId(): number | null {
  const [params] = useSearchParams()
  const value = params.get('draft')
  return value && /^\d+$/.test(value) ? Number(value) : null
}

export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: listProjects })
}

export function useWorkspace(projectId: number) {
  const draftId = useDraftId()
  // Keep showing the current draft while another one loads, so switching drafts doesn't blank the editor.
  return useQuery({ queryKey: keys.workspace(projectId, draftId), queryFn: () => getProjectWorkspace(projectId, draftId), placeholderData: keepPreviousData })
}

export function useStoryline(projectId: number) {
  return useQuery({ queryKey: keys.storyline(projectId), queryFn: () => storyApi.storyline(projectId) })
}

export function useCharacters(projectId: number) {
  return useQuery({ queryKey: keys.characters(projectId), queryFn: () => storyApi.characters(projectId) })
}

export function useTimeline(projectId: number, characterId?: number) {
  return useQuery({ queryKey: keys.timeline(projectId, characterId), queryFn: () => storyApi.timeline(projectId, characterId) })
}

export function useRelationships(projectId: number) {
  return useQuery({ queryKey: keys.relationships(projectId), queryFn: () => storyApi.relationships(projectId) })
}

export function useLocations(projectId: number) {
  return useQuery({ queryKey: keys.locations(projectId), queryFn: () => storyApi.locations(projectId) })
}

export function useBeats(projectId: number) {
  return useQuery({ queryKey: keys.beats(projectId), queryFn: () => storyApi.beats(projectId) })
}

export function useTwin(projectId: number) {
  return useQuery({ queryKey: keys.twin(projectId), queryFn: () => getStoryTwin(projectId) })
}

export function useArtifacts(projectId: number) {
  return useQuery({ queryKey: keys.artifacts(projectId), queryFn: () => listArtifacts(projectId) })
}

/** Turn any thrown value into a writer-facing message, explaining edit conflicts. */
export function errorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof ApiError && reason.status === 409) return `${reason.message}. Someone else changed this while you were editing — the latest version has been loaded.`
  return reason instanceof Error ? reason.message : fallback
}
