import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { AppRoutes } from '../App'

export type Call = { method: string; path: string; body: unknown; headers: Headers }
type Handler = (call: Call) => unknown
type Reply = { status?: number; body?: unknown }

/** A tiny fake API: register `"METHOD /path"` handlers; every request is recorded in `calls`. */
export function mockApi(routes: Record<string, Handler | object | string | number | null>) {
  const calls: Call[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://studio.test')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    const call = { method, path: url.pathname + url.search, body, headers: new Headers(init?.headers) }
    calls.push(call)
    const route = routes[`${method} ${url.pathname}${url.search}`] ?? routes[`${method} ${url.pathname}`]
    if (route === undefined) return new Response(JSON.stringify({ detail: 'Not mocked' }), { status: 404 })
    const result = typeof route === 'function' ? (route as Handler)(call) : route
    const isReply = result !== null && typeof result === 'object' && typeof (result as Reply).status === 'number' && !('id' in (result as object))
    const reply: Reply = isReply ? result as Reply : { body: result }
    if (reply.status === 204) return new Response(null, { status: 204 })
    return new Response(JSON.stringify(reply.body ?? {}), { status: reply.status ?? 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

/** Stand-in EventSource so tests can push live-sync events. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners = new Map<string, Set<(event: MessageEvent<string>) => void>>()
  closed = false
  constructor(public url: string) { FakeEventSource.instances.push(this) }
  addEventListener(kind: string, listener: (event: MessageEvent<string>) => void): void {
    if (!this.listeners.has(kind)) this.listeners.set(kind, new Set())
    this.listeners.get(kind)!.add(listener)
  }
  close(): void { this.closed = true }
  emit(kind: string, data: Record<string, unknown> = {}): void {
    const message = new MessageEvent('message', { data: JSON.stringify({ kind, project_id: 0, client: 'other-tab', at: '', data }) })
    this.listeners.get(kind)?.forEach(listener => listener(message))
  }
  static open(): FakeEventSource[] { return FakeEventSource.instances.filter(source => !source.closed) }
}

/** Render the studio's routes at `path` with a fresh query client. */
export function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return { ...view, client }
}

export const project = (id: number, extra: object = {}) => ({
  id, title: 'Lantern House', logline: null, description: null, genres: [], languages: ['English'], primary_language: 'English', project_instruction: '', version: 1, artwork_url: null, ...extra,
})

export const workspace = (id: number, extra: object = {}) => ({
  project: project(id),
  screenplay: { id: 12, project_id: id, title: 'Lantern House', format: 'feature', status: 'draft' },
  screenplays: [{ id: 12, project_id: id, title: 'Lantern House', format: 'feature', status: 'draft' }],
  acts: [{ id: 4, screenplay_id: 12, title: 'Act One', position: 0 }],
  scenes: [],
  blocks: {},
  ...extra,
})

export const character = (id: number, name: string, extra: object = {}) => ({
  id, project_id: 3, version: 1, position: 0, name, role: '', summary: '', bio: '', want: '', need: '', motive: '', objective: '', flaw: '', arc_summary: '', voice: '', notes: '',
  aliases: [], tags: [], cue: null, dialogue_lines: 0, scene_ids: [], source: 'writer', writer_edited: false, ...extra,
})

export const beat = (id: number, title: string, actId: number | null, position: number, extra: object = {}) => ({
  id, project_id: 3, version: 1, act_id: actId, position, title, summary: '', beat_type: 'beat', status: 'planned', scene_ids: [], character_ids: [], source: 'writer', ...extra,
})
