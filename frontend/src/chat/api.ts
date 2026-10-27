import type { Message } from '@ag-ui/core'
import { request } from '../api'

export type ChatThread = { id: string; project_id: number; title: string; role: string; created_at: string; updated_at: string }
export type ChatThreadDetail = ChatThread & { messages: Message[] }

/** Permission modes the dock offers, in the writer's words. */
export const CHAT_MODES = [
  { value: 'chat_only', label: 'Ask only' },
  { value: 'suggest', label: 'Propose' },
  { value: 'project_edit', label: 'Edit with approval' },
] as const
export type ChatMode = (typeof CHAT_MODES)[number]['value']

const threads = (projectId: number) => `/api/v1/projects/${projectId}/room/threads`

export const chatApi = {
  url: (projectId: number) => `/api/v1/projects/${projectId}/room/chat`,
  threads: (projectId: number) => request<ChatThread[]>(threads(projectId)),
  thread: (projectId: number, threadId: string) => request<ChatThreadDetail>(`${threads(projectId)}/${encodeURIComponent(threadId)}`),
  renameThread: (projectId: number, threadId: string, title: string) =>
    request<ChatThread>(`${threads(projectId)}/${encodeURIComponent(threadId)}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteThread: (projectId: number, threadId: string) =>
    request<void>(`${threads(projectId)}/${encodeURIComponent(threadId)}`, { method: 'DELETE' }),
}

/** A random id for threads, runs and messages (the client names its threads). */
export function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `id-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
