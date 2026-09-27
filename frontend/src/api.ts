export type Project = {
  id: number
  title: string
  logline: string | null
  description: string | null
  genres: string[]
  languages: string[]
  primary_language: string
  project_instruction: string
  version: number
  artwork_url: string | null
  references?: ProjectReference[]
}

export type ProjectReference = {
  id: number
  project_id: number
  kind: string
  label: string
  url?: string | null
  note?: string | null
  version: number
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

export type ProjectReferenceInput = Omit<ProjectReference, 'id' | 'project_id' | 'version'>

export type Scene = {
  id: number
  act_id: number
  heading: string
  position: number
  body: string
  version: number
  scene_instruction: string
}

export type ScreenplayBlock = {
  id: number
  scene_id: number
  position: number
  origin?: string
  element_type: string
  text: string
  character_extension: string | null
  is_dual: boolean
  dual_group: number | null
  translation: string | null
  translation_lang: string | null
}

export type Act = { id: number; screenplay_id: number; title: string | null; position: number }

export type SceneTiming = {
  scene_id: number
  position: number
  estimated_duration_seconds: number
  start_seconds: number
  end_seconds: number
}

export type ProjectWorkspace = {
  project: Project
  screenplay: { id: number; project_id: number; title: string; format: string; status: string; title_page?: Record<string, string> } | null
  screenplays?: { id: number; project_id: number; title: string; format: string; status: string }[]
  acts: Act[]
  scenes: Scene[]
  blocks: Record<number, ScreenplayBlock[]>
  timings?: SceneTiming[]
  total_runtime_seconds?: number
  target_runtime_seconds?: number
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

export type SceneRevision = {
  id: number
  scene_id: number
  rev_number: number
  message: string | null
  created_at: string
  snapshot?: Record<string, unknown>
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

export type Capability = { name: string; description: string; scope: string; mutates: boolean; approval_required: boolean }

export type WorkflowRun = { id: number; project_id: number; kind: string; status: string; input?: Record<string, unknown>; result: Record<string, unknown> | null; error: string | null; attempt_count: number; max_attempts: number; created_at?: string; updated_at?: string }

export type ContextWorkflowSpec = { key: string; label: string; description: string; input_artifact_kinds: string[]; output_kind: string; evaluator: string; agent_role: string; permission_mode: string }

export type EvaluationResult = { id: number; project_id: number; target_kind: string; target_id: number | null; evaluator: string; score: number | null; summary: string; findings: Record<string, unknown>; created_at: string }

export type CopilotRunResponse = { message: CopilotMessage; run: WorkflowRun }

export const AUTH_REQUIRED_EVENT = 'draftpilot:auth-required'

/** Identify this browser tab so it can ignore live-sync echoes of its own edits. */
export const CLIENT_ID: string = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type') && !(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  headers.set('X-DraftPilot-Client', CLIENT_ID)
  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  if (response.status === 401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT))
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try { const body = await response.json(); if (typeof body?.detail === 'string') detail = body.detail } catch { /* non-JSON error body */ }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/api/v1/projects')
}

export type WizardAssistRequest = {
  prompt: string
  target_format?: string
  primary_language?: string
  genre_preference?: string | null
}

export type WizardAssistCharacter = {
  name: string
  role: string
  description: string
}

export type WizardAssistResponse = {
  title: string
  logline: string
  description: string
  story_outline: string
  genres: string[]
  target_audience: string
  characters: WizardAssistCharacter[]
  visual_style: string
  camera_type: string
  screening_type: string
  primary_language: string
  format: string
}

export function assistProjectWizard(payload: WizardAssistRequest): Promise<WizardAssistResponse> {
  return request<WizardAssistResponse>('/api/v1/projects/wizard/assist', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createProject(payload: ProjectCreatePayload): Promise<Project> {
  return request<Project>('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function uploadProjectArtwork(projectId: number, file: File): Promise<Project> {
  const body = new FormData()
  body.append('artwork', file)
  return request<Project>(`/api/v1/projects/${projectId}/artwork`, { method: 'POST', body })
}

/** Return the draft selected in the URL (`?draft=<screenplay id>`), if any. */
export function selectedDraftId(): number | null {
  const value = new URLSearchParams(window.location.search).get('draft')
  return value && /^\d+$/.test(value) ? Number(value) : null
}

/** Select a draft in the URL without reloading the page. */
export function selectDraft(screenplayId: number): void {
  const url = new URL(window.location.href)
  url.searchParams.set('draft', String(screenplayId))
  window.history.replaceState(null, '', url)
}

export function getProjectWorkspace(projectId: number, screenplayId: number | null = selectedDraftId()): Promise<ProjectWorkspace> {
  const query = screenplayId === null ? '' : `?screenplay_id=${screenplayId}`
  return request<ProjectWorkspace>(`/api/v1/projects/${projectId}/workspace${query}`)
}

export function createProjectScene(projectId: number, screenplayId: number, actId: number, heading: string, position = 0): Promise<Scene> {
  return request<Scene>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/scenes`, { method: 'POST', body: JSON.stringify({ act_id: actId, heading, position }) })
}

export function createProjectBlock(projectId: number, sceneId: number, version: number, elementType: string, text: string): Promise<ScreenplayBlock> {
  return request<ScreenplayBlock>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks`, { method: 'POST', headers: { 'If-Match': String(version) }, body: JSON.stringify({ element_type: elementType, text }) })
}

export function deleteProjectBlock(projectId: number, sceneId: number, blockId: number, version: number): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/${blockId}`, { method: 'DELETE', headers: { 'If-Match': String(version) } })
}

export function reorderProjectBlocks(projectId: number, sceneId: number, version: number, blockIds: number[]): Promise<ScreenplayBlock[]> {
  return request<ScreenplayBlock[]>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/order`, { method: 'PUT', headers: { 'If-Match': String(version) }, body: JSON.stringify({ block_ids: blockIds }) })
}

export type ProjectEvent = { kind: string; project_id: number; client: string | null; at: string; data: Record<string, unknown> }

export const PROJECT_EVENT_KINDS = ['scene.changed', 'screenplay.changed', 'proposal.changed', 'timeline.changed', 'translation.changed', 'artifact.changed', 'approval.changed', 'run.changed', 'workflow.progress'] as const

/** Subscribe to a project's live change stream; returns an unsubscribe function. */
export function subscribeProjectEvents(projectId: number, onEvent: (event: ProjectEvent) => void): () => void {
  if (typeof EventSource === 'undefined') return () => undefined
  const source = new EventSource(`/api/v1/projects/${projectId}/events`, { withCredentials: true })
  const handler = (message: MessageEvent<string>) => {
    try { onEvent(JSON.parse(message.data) as ProjectEvent) } catch { /* ignore malformed frames */ }
  }
  PROJECT_EVENT_KINDS.forEach(kind => source.addEventListener(kind, handler as EventListener))
  return () => source.close()
}

export function createTimelineProposal(projectId: number, screenplayId: number, sceneIds: number[], durations: Record<number, number>): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals`, { method: 'POST', body: JSON.stringify({ scene_ids: sceneIds, durations }) })
}

export function listTimelineProposals(projectId: number, screenplayId: number): Promise<TimelineProposal[]> {
  return request<TimelineProposal[]>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals`)
}

export function approveTimelineProposal(projectId: number, screenplayId: number, proposalId: number): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals/${proposalId}/approve`, { method: 'POST' })
}

export function rejectTimelineProposal(projectId: number, screenplayId: number, proposalId: number): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals/${proposalId}/reject`, { method: 'POST' })
}

export function rollbackTimelineProposal(projectId: number, screenplayId: number, proposalId: number): Promise<TimelineProposal> {
  return request<TimelineProposal>(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/timeline/proposals/${proposalId}/rollback`, { method: 'POST' })
}

export function getAgentProposals(projectId: number): Promise<AgentProposal[]> {
  return request<AgentProposal[]>(`/api/v1/projects/${projectId}/agent-proposals`)
}

export function createAgentProposal(projectId: number, payload: { target_kind: 'scene' | 'block' | 'artifact' | 'dialogue_translation'; target_id: number; scene_id?: number; operation: Record<string, unknown>; diff?: Record<string, unknown>; base_version: number }): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals`, { method: 'POST', body: JSON.stringify(payload) })
}

export function approveAgentProposal(projectId: number, proposalId: number): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals/${proposalId}/approve`, { method: 'POST' })
}

export function rejectAgentProposal(projectId: number, proposalId: number): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals/${proposalId}/reject`, { method: 'POST' })
}

export type AuthStatus = { auth_required: boolean; authenticated: boolean }

export function getAuthStatus(): Promise<AuthStatus> {
  return request<AuthStatus>('/api/v1/auth/status')
}

export function signIn(token: string): Promise<AuthStatus> {
  return request<AuthStatus>('/api/v1/auth/session', { method: 'POST', body: JSON.stringify({ token }) })
}

export function signOut(): Promise<void> {
  return request<void>('/api/v1/auth/session', { method: 'DELETE' })
}

export type McpApproval = {
  id: number
  client_id: string
  project_id: number
  capability: string
  action: string
  summary: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected' | 'consumed' | 'expired'
  created_at: string
  expires_at: string
  decided_at: string | null
}

export function listMcpApprovals(projectId: number, state?: McpApproval['status']): Promise<McpApproval[]> {
  const query = state ? `?state=${state}` : ''
  return request<McpApproval[]>(`/api/v1/projects/${projectId}/mcp-approvals${query}`)
}

export function decideMcpApproval(projectId: number, approvalId: number, decision: 'approve' | 'reject'): Promise<McpApproval> {
  return request<McpApproval>(`/api/v1/projects/${projectId}/mcp-approvals/${approvalId}/${decision}`, { method: 'POST' })
}

export function rollbackAgentProposal(projectId: number, proposalId: number): Promise<AgentProposal> {
  return request<AgentProposal>(`/api/v1/projects/${projectId}/agent-proposals/${proposalId}/rollback`, { method: 'POST' })
}

export function updateProjectBlock(projectId: number, sceneId: number, blockId: number, version: number, changes: { text?: string; element_type?: string; is_dual?: boolean; dual_group?: number | null }): Promise<ScreenplayBlock> {
  return request<ScreenplayBlock>(`/api/v1/projects/${projectId}/scenes/${sceneId}/blocks/${blockId}`, {
    method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes),
  })
}

export function updateProjectScene(projectId: number, sceneId: number, version: number, changes: { heading?: string; scene_instruction?: string }): Promise<Scene> {
  return request<Scene>(`/api/v1/projects/${projectId}/scenes/${sceneId}`, {
    method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes),
  })
}

export function updateProject(projectId: number, version: number, projectInstruction: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}`, {
    method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify({ project_instruction: projectInstruction }),
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

export function listSceneRevisions(projectId: number, sceneId: number): Promise<SceneRevision[]> {
  return request<SceneRevision[]>(`/api/v1/projects/${projectId}/scenes/${sceneId}/revisions`)
}

export function createSceneRevision(projectId: number, sceneId: number, message: string): Promise<SceneRevision> {
  return request<SceneRevision>(`/api/v1/projects/${projectId}/scenes/${sceneId}/revisions`, { method: 'POST', body: JSON.stringify({ message }) })
}

export function diffSceneRevisions(projectId: number, sceneId: number, fromId: number, toId: number): Promise<{ diff: string }> {
  return request<{ diff: string }>(`/api/v1/projects/${projectId}/scenes/${sceneId}/revisions/${fromId}/diff/${toId}`)
}

export function restoreSceneRevision(projectId: number, sceneId: number, revisionId: number, version: number, sections: Array<'heading' | 'blocks'>): Promise<Scene> {
  return request<Scene>(`/api/v1/projects/${projectId}/scenes/${sceneId}/revisions/${revisionId}/restore`, { method: 'POST', headers: { 'If-Match': String(version) }, body: JSON.stringify({ sections }) })
}

export function listArtifacts(projectId: number): Promise<StoryArtifact[]> {
  return request<StoryArtifact[]>(`/api/v1/projects/${projectId}/artifacts`)
}

export function listContextWorkflows(projectId: number): Promise<ContextWorkflowSpec[]> {
  return request<ContextWorkflowSpec[]>(`/api/v1/projects/${projectId}/context/workflows`)
}

export function startContextWorkflow(projectId: number, workflow: string, artifactId: number, instruction: string, permissionMode = 'suggest'): Promise<WorkflowRun> {
  return request<WorkflowRun>(`/api/v1/projects/${projectId}/context/workflows/runs`, { method: 'POST', body: JSON.stringify({ workflow, artifact_id: artifactId, instruction, permission_mode: permissionMode }) })
}

export function applyContextSuggestion(projectId: number, runId: number, expectedSourceVersion: number): Promise<KnowledgeGraph['nodes'][number]> {
  return request<KnowledgeGraph['nodes'][number]>(`/api/v1/projects/${projectId}/context/workflows/runs/${runId}/apply`, { method: 'POST', body: JSON.stringify({ expected_source_version: expectedSourceVersion }) })
}

export function listEvaluations(projectId: number): Promise<EvaluationResult[]> {
  return request<EvaluationResult[]>(`/api/v1/projects/${projectId}/evaluations`)
}

export function startEvaluation(projectId: number, screenplayId: number, evaluator = 'deterministic_review'): Promise<WorkflowRun> {
  return request<WorkflowRun>(`/api/v1/projects/${projectId}/evaluations/runs`, { method: 'POST', body: JSON.stringify({ screenplay_id: screenplayId, evaluator }) })
}

export function createArtifact(projectId: number, kind: string, title: string, dependsOn: number[] = []): Promise<StoryArtifact> {
  return request<StoryArtifact>(`/api/v1/projects/${projectId}/artifacts`, { method: 'POST', body: JSON.stringify({ kind, title, depends_on: dependsOn }) })
}

export function updateArtifact(projectId: number, artifactId: number, version: number, changes: { title?: string; content?: string }): Promise<StoryArtifact> {
  return request<StoryArtifact>(`/api/v1/projects/${projectId}/artifacts/${artifactId}`, { method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes) })
}

export function applyStoryOperation(projectId: number, artifactId: number, version: number, operation: string, payload: Record<string, unknown>): Promise<StoryArtifact> {
  return request<StoryArtifact>(`/api/v1/projects/${projectId}/artifacts/${artifactId}/operations`, { method: 'POST', headers: { 'If-Match': String(version) }, body: JSON.stringify({ operation, payload }) })
}

export function createProjectBackup(projectId: number): Promise<ProjectBackup> {
  return request<ProjectBackup>(`/api/v1/projects/${projectId}/backups`, { method: 'POST' })
}

export function listProjectBackups(projectId: number): Promise<ProjectBackup[]> {
  return request<ProjectBackup[]>(`/api/v1/projects/${projectId}/backups`)
}

export function restoreProjectBackup(projectId: number, filename: string): Promise<{ project_id: number }> {
  return request<{ project_id: number }>(`/api/v1/projects/${projectId}/backups/${encodeURIComponent(filename)}/restore`, { method: 'POST' })
}

export async function importScreenplay(projectId: number, screenplayId: number, format: 'fountain' | 'fdx' | 'pdf', content: string | ArrayBuffer): Promise<{ id: number; title: string; format: string; status: string; project_id: number }> {
  const response = await fetch(`/api/v1/projects/${projectId}/screenplays/${screenplayId}/imports/${format}`, {
    method: 'POST', headers: { 'Content-Type': format === 'fdx' ? 'application/xml' : format === 'pdf' ? 'application/pdf' : 'text/plain' }, body: content,
  })
  if (!response.ok) throw new Error(`Import failed (${response.status})`)
  return response.json() as Promise<{ id: number; title: string; format: string; status: string; project_id: number }>
}

export function listProviderProfiles(): Promise<ProviderProfile[]> {
  return request<ProviderProfile[]>('/api/v1/settings/providers')
}

export function listCapabilities(page: string): Promise<Capability[]> {
  return request<Capability[]>(`/api/v1/capabilities?page=${encodeURIComponent(page)}`)
}

export function createProviderProfile(payload: { name: string; provider: string; model: string; base_url?: string; enabled: boolean; api_key?: string }): Promise<ProviderProfile> {
  return request<ProviderProfile>('/api/v1/settings/providers', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateProviderProfile(profileId: number, payload: { provider?: string; model?: string; base_url?: string; enabled?: boolean; api_key?: string }): Promise<ProviderProfile> {
  return request<ProviderProfile>(`/api/v1/settings/providers/${profileId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export type WriterProfile = { name: string; pen_name: string; bio: string; default_format: string; default_language: string; style_notes: string; preferences: Record<string, unknown>; updated_at?: string | null }
export type WriterMemory = { id: number; kind: string; text: string; source: string; pinned: boolean; project_id: number | null; created_at: string }

export function getWriterProfile(): Promise<WriterProfile> {
  return request<WriterProfile>('/api/v1/writer/profile')
}

export function saveWriterProfile(profile: WriterProfile): Promise<WriterProfile> {
  return request<WriterProfile>('/api/v1/writer/profile', { method: 'PUT', body: JSON.stringify(profile) })
}

export function listWriterMemories(projectId?: number): Promise<WriterMemory[]> {
  return request<WriterMemory[]>(`/api/v1/writer/memories${projectId ? `?project_id=${projectId}` : ''}`)
}

export function addWriterMemory(memory: { kind: string; text: string; pinned?: boolean; project_id?: number | null }): Promise<WriterMemory> {
  return request<WriterMemory>('/api/v1/writer/memories', { method: 'POST', body: JSON.stringify({ source: 'writer', pinned: false, ...memory }) })
}

export function forgetWriterMemory(memoryId: number): Promise<void> {
  return request<void>(`/api/v1/writer/memories/${memoryId}`, { method: 'DELETE' })
}

export type ModelOption = { id: string; loaded: boolean; kind: string }

export function listDefaultModels(): Promise<ModelOption[]> {
  return request<ModelOption[]>('/api/v1/settings/providers/default/models')
}

export function listProfileModels(profileId: number): Promise<ModelOption[]> {
  return request<ModelOption[]>(`/api/v1/settings/providers/${profileId}/models`)
}

export function testProviderProfile(profileId: number): Promise<{ ok: boolean; message: string; latency_ms: number | null }> {
  return request<{ ok: boolean; message: string; latency_ms: number | null }>(`/api/v1/settings/providers/${profileId}/test`, { method: 'POST' })
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

export function listProjectReferences(projectId: number): Promise<ProjectReference[]> {
  return request<ProjectReference[]>(`/api/v1/projects/${projectId}/references`)
}

export function updateProjectReference(projectId: number, referenceId: number, version: number, changes: Partial<Pick<ProjectReference, 'kind' | 'label' | 'url' | 'note'>>): Promise<ProjectReference> {
  return request<ProjectReference>(`/api/v1/projects/${projectId}/references/${referenceId}`, {
    method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes),
  })
}

export function deleteProjectReference(projectId: number, referenceId: number): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}/references/${referenceId}`, { method: 'DELETE' })
}

export function createKnowledgeNode(projectId: number, kind: string, label: string, description: string): Promise<KnowledgeGraph['nodes'][number]> {
  return request<KnowledgeGraph['nodes'][number]>(`/api/v1/projects/${projectId}/knowledge-graph/nodes`, { method: 'POST', body: JSON.stringify({ kind, label, description: description || null }) })
}

export function updateKnowledgeNode(projectId: number, nodeId: number, version: number, changes: { label?: string; description?: string | null }): Promise<KnowledgeGraph['nodes'][number]> {
  return request<KnowledgeGraph['nodes'][number]>(`/api/v1/projects/${projectId}/knowledge-graph/nodes/${nodeId}`, { method: 'PATCH', headers: { 'If-Match': String(version) }, body: JSON.stringify(changes) })
}

export function createKnowledgeEdge(projectId: number, sourceNodeId: number, targetNodeId: number, relation: string): Promise<KnowledgeGraph['edges'][number]> {
  return request<KnowledgeGraph['edges'][number]>(`/api/v1/projects/${projectId}/knowledge-graph/edges`, { method: 'POST', body: JSON.stringify({ source_node_id: sourceNodeId, target_node_id: targetNodeId, relation }) })
}

export function deleteKnowledgeEdge(projectId: number, edgeId: number): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}/knowledge-graph/edges/${edgeId}`, { method: 'DELETE' })
}

export function getAgentRoles(): Promise<AgentRole[]> {
  return request<AgentRole[]>('/api/v1/agents/roles')
}

export type JsonSchema = { type?: string; title?: string; description?: string; default?: unknown; minimum?: number; maximum?: number; maxLength?: number; items?: JsonSchema; properties?: Record<string, JsonSchema>; required?: string[]; anyOf?: JsonSchema[]; $ref?: string }

export type RoomWorkflow = { key: string; label: string; description: string; roles: string[]; proposes: boolean; params_schema: JsonSchema }

export function listRoomWorkflows(projectId: number): Promise<RoomWorkflow[]> {
  return request<RoomWorkflow[]>(`/api/v1/projects/${projectId}/room/workflows`)
}

export function startRoomWorkflow(projectId: number, workflow: string, params: Record<string, unknown>, providerProfileId: number | null = null): Promise<WorkflowRun> {
  return request<WorkflowRun>(`/api/v1/projects/${projectId}/room/workflows`, { method: 'POST', body: JSON.stringify({ workflow, params, provider_profile_id: providerProfileId }) })
}

export function listWorkflowRuns(projectId: number): Promise<WorkflowRun[]> {
  return request<WorkflowRun[]>(`/api/v1/projects/${projectId}/runs`)
}

export type WorkflowInsight = { runs: number; succeeded: number; failed: number; approved: number; rejected: number; rolled_back: number; pending: number; up: number; down: number; acceptance: number | null; retention: number | null; thumbs_up_share: number | null; usefulness: number | null; mean_duration_s: number | null }
export type RoleInsight = { runs: number; failure_rate: number | null; tokens: number; mean_duration_s: number | null }
export type Insights = { workflows: Record<string, WorkflowInsight>; roles: Record<string, RoleInsight> }

export function getInsights(projectId: number): Promise<Insights> {
  return request<Insights>(`/api/v1/projects/${projectId}/insights`)
}

export function giveFeedback(projectId: number, target: { workflow_run_id?: number; agent_run_id?: number }, rating: 1 | -1, comment = ''): Promise<unknown> {
  return request<unknown>(`/api/v1/projects/${projectId}/feedback`, { method: 'POST', body: JSON.stringify({ ...target, rating, comment }) })
}

export type DeletedProject = { project_id: number; title: string; filename: string; deleted_at: string }

export function deleteProject(projectId: number): Promise<{ project_id: number; title: string; backup: string; removed: Record<string, number> }> {
  return request(`/api/v1/projects/${projectId}`, { method: 'DELETE' })
}

export function duplicateProject(projectId: number, title?: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}/duplicate`, { method: 'POST', body: JSON.stringify(title ? { title } : {}) })
}

export function listDeletedProjects(): Promise<DeletedProject[]> {
  return request<DeletedProject[]>('/api/v1/projects/deleted')
}

export type TwinNode = KnowledgeGraph['nodes'][number] & { node_metadata: Record<string, unknown> }
export type StoryTwin = { screenplay_id: number | null; characters: TwinNode[]; locations: TwinNode[]; canon: TwinNode[]; brief: string }

export function getStoryTwin(projectId: number): Promise<StoryTwin> {
  return request<StoryTwin>(`/api/v1/projects/${projectId}/twin`)
}

export function refreshStoryTwin(projectId: number): Promise<Record<string, number>> {
  return request<Record<string, number>>(`/api/v1/projects/${projectId}/twin/refresh`, { method: 'POST' })
}
