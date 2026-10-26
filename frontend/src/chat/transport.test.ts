import { describe, expect, it, vi } from 'vitest'
import { sse } from '../test/harness'
import { streamRun } from './transport'


describe('streamRun', () => {
  it('parses an AG-UI SSE body into events', async () => {
    const fetchMock = vi.fn(async () => sse([{ type: 'RUN_STARTED', threadId: 't', runId: 'r' }, { type: 'TEXT_MESSAGE_START', messageId: 'm', role: 'assistant' }, { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'Hi' }, { type: 'TEXT_MESSAGE_END', messageId: 'm' }, { type: 'RUN_FINISHED', threadId: 't', runId: 'r', outcome: { type: 'success' } }]))
    vi.stubGlobal('fetch', fetchMock)
    const events: string[] = []
    await streamRun('/chat', { threadId: 't', runId: 'r', messages: [], tools: [], context: [], state: {}, forwardedProps: { role: 'showrunner' } }, event => events.push(event.type), new AbortController().signal)
    expect(events).toEqual(['RUN_STARTED', 'TEXT_MESSAGE_START', 'TEXT_MESSAGE_CONTENT', 'TEXT_MESSAGE_END', 'RUN_FINISHED'])
    const init = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const body = JSON.parse(String(init[1].body))
    expect(body.forwardedProps).toEqual({ role: 'showrunner' })
    expect(new Headers(init[1].headers).get('X-DraftPilot-Client')).toBeTruthy()
  })

  it('surfaces API errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'No LLM provider is enabled' }), { status: 503 })))
    await expect(streamRun('/chat', { threadId: 't', runId: 'r', messages: [], tools: [], context: [] }, () => undefined, new AbortController().signal)).rejects.toThrow('No LLM provider is enabled')
  })
})
