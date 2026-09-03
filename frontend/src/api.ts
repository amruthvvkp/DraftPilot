export type Project = {
  id: number
  title: string
  logline: string | null
  description: string | null
  genres: string[]
  languages: string[]
  primary_language: string
  artwork_url: string | null
  references?: ProjectReference[]
}

export type ProjectReference = {
  id?: number
  project_id?: number
  kind: string
  label: string
  url?: string | null
  note?: string | null
}

export type ProjectCreatePayload = {
  title: string
  logline?: string | null
  description?: string | null
  story_outline?: string | null
  visual_style?: string | null
  camera_type?: string | null
  screening_type?: string | null
  artwork_url?: string | null
  genres: string[]
  languages: string[]
  primary_language: string
  references?: ProjectReferenceInput[]
}

export type ProjectReferenceInput = Omit<ProjectReference, 'id' | 'project_id'>

export type Scene = {
  id: number
  act_id: number
  heading: string
  position: number
  body: string
  version: number
}

export type ScreenplayBlock = {
  id: number
  scene_id: number
  position: number
  element_type: string
  text: string
  character_extension: string | null
  is_dual: boolean
  dual_group: number | null
  translation: string | null
  translation_lang: string | null
}

export type Act = { id: number; screenplay_id: number; title: string | null; position: number }

export type ProjectWorkspace = {
  project: Project
  screenplay: { id: number; project_id: number; title: string; format: string; status: string } | null
  acts: Act[]
  scenes: Scene[]
  blocks: Record<number, ScreenplayBlock[]>
}

export type TimelineProposal = {
  id: number
  project_id: number
  screenplay_id: number
  status: string
  original_scene_ids: number[]
  proposed_scene_ids: number[]
  timings: Array<{ scene_id: number; position: number; start_seconds: number; end_seconds: number }>
  total_runtime_seconds: number
}

export type AgentProposal = {
  id: number
  project_id: number
  run_id: number | null
  target_kind: string
  target_id: number
  operation: Record<string, unknown>
  diff: Record<string, unknown>
  before: Record<string, unknown>
  base_version: number
  status: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json() as Promise<T>
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/api/v1/projects')
}

export function createProject(payload: ProjectCreatePayload): Promise<Project> {
  return request<Project>('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getProjectWorkspace(projectId: number): Promise<ProjectWorkspace> {
  return request<ProjectWorkspace>(`/api/v1/projects/${projectId}/workspace`)
}

export function createTimelineProposal(projectId: number, screenplayId: number, sceneIds: number[], durations: Record<number, number>): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals`, { method: 'POST', body: JSON.stringify({ scene_ids: sceneIds, durations }) })
}

export function approveTimelineProposal(projectId: number, screenplayId: number, proposalId: number): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals/${proposalId}/approve`, { method: 'POST' })
}

export function getAgentProposals(projectId: number): Promise<AgentProposal[]> {
  return request<AgentProposal[]>(`/api/v1/projects/${projectId}/agent-proposals`)
}

export function approveAgentProposal(projectId: number, proposalId: number): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals/${proposalId}/approve`, { method: 'POST' })
}

export function rollbackAgentProposal(projectId: number, proposalId: number): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals/${proposalId}/rollback`, { method: 'POST' })
}

export function updateProjectBlock(projectId: number, sceneId: number, blockId: number, version: number, text: string): Promise<ScreenplayBlock> {
  return request<ScreenplayBlock>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/${blockId}`, {
    method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify({ text }),
  })
}
