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

export type DialogueTranslation = {
  id: number
  block_id: number
  language: string
  text: string
  source_version: number
  status: string
}

export type StoryArtifact = {
  id: number
  project_id: number
  kind: string
  title: string
  content: string
  version: number
  stale: boolean
  depends_on: number[]
  artifact_metadata: Record<string, unknown>
}

export type ProjectBackup = {
  filename: string
  manifest: { schema_version: number; project_id: number; created_at: string; app_version: string; sha256: string }
}

export type ProviderProfile = {
  id: number
  name: string
  provider: string
  model: string
  base_url: string | null
  enabled: boolean
  has_api_key: boolean
}

export type CopilotMessage = {
  id: number
  project_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  page: string
  artifact: string | null
  selection: string | null
  instruction_layers: Record<string, unknown>
  citations: Array<Record<string, unknown>>
  active_tools: string[]
  created_at: string
}

export type KnowledgeGraph = {
  nodes: Array<{ id: number; project_id: number; kind: string; label: string; description: string | null; node_metadata: Record<string, unknown>; version: number }>
  edges: Array<{ id: number; project_id: number; source_node_id: number; target_node_id: number; relation: string; edge_metadata: Record<string, unknown> }>
}

export type AgentRole = { key: string; label: string; description: string; default_permission: 'chat_only' | 'suggest' | 'scoped_edit' | 'project_edit' }

export type WorkflowRun = { id: number; project_id: number; kind: string; status: string; result: Record<string, unknown> | null; error: string | null }

export type CopilotRunResponse = { message: CopilotMessage; run: WorkflowRun }

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

export function getDialogueTranslations(projectId: number, sceneId: number, blockId: number): Promise<DialogueTranslation[]> {
  return request<DialogueTranslation[]>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/${blockId}/translations`)
}

export function saveDialogueTranslation(projectId: number, sceneId: number, blockId: number, language: string, version: number, text: string): Promise<DialogueTranslation> {
  return request<DialogueTranslation>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/${blockId}/translations/${encodeURIComponent(language)}`, {
    method: 'PUT', headers: { 'If-Match': String(version) }, body: JSON.stringify({ text }),
  })
}

export function listArtifacts(projectId: number): Promise<StoryArtifact[]> {
  return request<StoryArtifact[]>(`/api/v1/projects/${projectId}/artifacts`)
}

export function createArtifact(projectId: number, kind: string, title: string): Promise<StoryArtifact> {
  return request<StoryArtifact>(`/api/v1/projects/${projectId}/artifacts`, { method: 'POST', body: JSON.stringify({ kind, title }) })
}

export function updateArtifact(projectId: number, artifactId: number, version: number, changes: { title?: string; content?: string }): Promise<StoryArtifact> {
  return request<StoryArtifact>(`/api/v1/projects/${projectId}/artifacts/${artifactId}`, { method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes) })
}

export function createProjectBackup(projectId: number): Promise<ProjectBackup> {
  return request<ProjectBackup>(`/api/v1/projects/${projectId}/backups`, { method: 'POST' })
}

export async function importScreenplay(projectId: number, screenplayId: number, format: 'fountain' | 'fdx', content: string): Promise<{ id: number; title: string; format: string; status: string; project_id: number }> {
  const response = await fetch(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/imports/${format}`, {
    method: 'POST', headers: { 'Content-Type': format === 'fdx' ? 'application/xml' : 'text/plain' }, body: content,
  })
  if (!response.ok) throw new Error(`Import failed (${response.status})`)
  return response.json() as Promise<{ id: number; title: string; format: string; status: string; project_id: number }>
}

export function listProviderProfiles(): Promise<ProviderProfile[]> {
  return request<ProviderProfile[]>('/api/v1/settings/providers')
}

export function createProviderProfile(payload: { name: string; provider: string; model: string; base_url?: string; enabled: boolean; api_key?: string }): Promise<ProviderProfile> {
  return request<ProviderProfile>('/api/v1/settings/providers', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateProviderProfile(profileId: number, payload: { provider?: string; model?: string; base_url?: string; enabled?: boolean; api_key?: string }): Promise<ProviderProfile> {
  return request<ProviderProfile>(`/api/v1/settings/providers/${profileId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function cancelWorkflowRun(projectId: number, runId: number): Promise<{ id: number; project_id: number; status: string }> {
  return request<{ id: number; project_id: number; status: string }>(`/api/v1/projects/${projectId}/runs/${runId}/cancel`, { method: 'POST' })
}

export function getCopilotMessages(projectId: number): Promise<CopilotMessage[]> {
  return request<CopilotMessage[]>(`/api/v1/projects/${projectId}/copilot/messages`)
}

export function sendCopilotMessage(projectId: number, payload: Pick<CopilotMessage, 'content' | 'page' | 'artifact' | 'selection' | 'instruction_layers' | 'citations' | 'active_tools'>): Promise<CopilotMessage> {
  return request<CopilotMessage>(`/api/v1/projects/${projectId}/copilot/messages`, { method: 'POST', body: JSON.stringify({ ...payload, role: 'user' }) })
}

export function requestCopilotReply(projectId: number, payload: Pick<CopilotMessage, 'content' | 'page' | 'artifact' | 'selection' | 'instruction_layers' | 'citations' | 'active_tools'>): Promise<CopilotMessage> {
  return request<CopilotMessage>(`/api/v1/projects/${projectId}/copilot/messages/respond`, { method: 'POST', body: JSON.stringify({ ...payload, role: 'user' }) })
}

export function startCopilotRun(projectId: number, payload: Pick<CopilotMessage, 'content' | 'page' | 'artifact' | 'selection' | 'instruction_layers' | 'citations' | 'active_tools'>): Promise<CopilotRunResponse> {
  return request<CopilotRunResponse>(`/api/v1/projects/${projectId}/copilot/messages/respond-async`, { method: 'POST', body: JSON.stringify({ ...payload, role: 'user' }) })
}

export function getWorkflowRun(projectId: number, runId: number): Promise<WorkflowRun> {
  return request<WorkflowRun>(`/api/v1/projects/${projectId}/runs/${runId}`)
}

export function getKnowledgeGraph(projectId: number): Promise<KnowledgeGraph> {
  return request<KnowledgeGraph>(`/api/v1/projects/${projectId}/knowledge-graph`)
}

export function getAgentRoles(): Promise<AgentRole[]> {
  return request<AgentRole[]>('/api/v1/agents/roles')
}
