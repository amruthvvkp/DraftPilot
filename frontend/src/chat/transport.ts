import { HttpAgent } from '@ag-ui/client'
import type { RunAgentInput } from '@ag-ui/core'
import { ApiError, AUTH_REQUIRED_EVENT, CLIENT_ID } from '../api'
import type { ChatEvent } from './reducer'

/** Fetch for the chat stream: same-origin credentials, the tab id, and API errors as ApiError. */
async function chatFetch(url: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('X-DraftPilot-Client', CLIENT_ID)
  const response = await fetch(url, { ...init, headers, credentials: 'same-origin' })
  if (response.status === 401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT))
  if (!response.ok) {
    let detail = `The room could not answer (${response.status})`
    try { const body = await response.json(); if (typeof body?.detail === 'string') detail = body.detail } catch { /* non-JSON error body */ }
    throw new ApiError(response.status, detail)
  }
  return response
}

/**
 * Stream one AG-UI run. Events go to `onEvent` as they arrive; the promise settles when the stream ends,
 * rejects on a transport error, and resolves quietly when `signal` aborts (Stop).
 */
export function streamRun(url: string, input: RunAgentInput, onEvent: (event: ChatEvent) => void, signal: AbortSignal): Promise<void> {
  const agent = new HttpAgent({ url, fetch: chatFetch })
  const controller = new AbortController()
  agent.abortController = controller
  return new Promise((resolve, reject) => {
    if (signal.aborted) { resolve(); return }
    const subscription = agent.run(input).subscribe({
      next: event => onEvent(event as unknown as ChatEvent),
      error: (error: unknown) => (signal.aborted ? resolve() : reject(error)),
      complete: () => resolve(),
    })
    signal.addEventListener('abort', () => { subscription.unsubscribe(); controller.abort(); resolve() }, { once: true })
  })
}
