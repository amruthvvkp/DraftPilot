import { describe, expect, it } from 'vitest'
import {
  allDecided, type ChatAction, type ChatEvent, chatReducer, type ChatState, entriesFromMessages, initialChatState,
  pendingFrontendCalls, resumeEntries, type ToolEntry, toolResultMessages,
} from './reducer'

const run = (state: ChatState, ...events: ChatEvent[]) => events.reduce((current, event) => chatReducer(current, { type: 'event', event }), state)
const apply = (state: ChatState, ...actions: ChatAction[]) => actions.reduce(chatReducer, state)
const tool = (state: ChatState, id: string) => state.entries.find((entry): entry is ToolEntry => entry.kind === 'tool' && entry.id === id)!

const interruptRun: ChatEvent[] = [
  { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
  { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'create_story_entity', parentMessageId: 'a1' },
  { type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{"kind": "character", ' },
  { type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '"fields": {"name": "Karl"}}' },
  { type: 'TOOL_CALL_END', toolCallId: 'c1' },
  { type: 'RUN_FINISHED', threadId: 't', runId: 'r1', outcome: { type: 'interrupt', interrupts: [{ id: 'int-c1', reason: 'tool_call', toolCallId: 'c1', message: 'Approve?' }] } },
]

describe('chatReducer', () => {
  it('streams text into one assistant message and ignores empty messages', () => {
    const state = run(apply(initialChatState, { type: 'user', id: 'u1', text: 'Open on the river?' }),
      { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
      { type: 'TEXT_MESSAGE_START', messageId: 'empty', role: 'assistant' },
      { type: 'TEXT_MESSAGE_END', messageId: 'empty' },
      { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Open ' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'on the **river**.' },
      { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
      { type: 'RUN_FINISHED', threadId: 't', runId: 'r1', outcome: { type: 'success' } })
    expect(state.entries).toEqual([{ kind: 'user', id: 'u1', text: 'Open on the river?' }, { kind: 'text', id: 'm1', text: 'Open on the **river**.' }])
    expect(state.status).toBe('idle')
  })

  it('tracks a tool call from streaming arguments to its result, and reasoning', () => {
    const state = run(initialChatState,
      { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
      { type: 'REASONING_MESSAGE_CONTENT', messageId: 'th', delta: 'Check the twin first.' },
      { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'read_project_overview', parentMessageId: 'a1' },
      { type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{"project_id": 1}' })
    expect(tool(state, 'c1')).toMatchObject({ name: 'read_project_overview', status: 'streaming', args: '{"project_id": 1}', runId: 'r1' })
    const ended = run(state, { type: 'TOOL_CALL_END', toolCallId: 'c1' })
    expect(tool(ended, 'c1').status).toBe('called')
    const done = run(ended, { type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'x', content: '{"project": {}}' })
    expect(tool(done, 'c1')).toMatchObject({ status: 'done', result: '{"project": {}}' })
    expect(done.entries[0]).toEqual({ kind: 'reasoning', id: 'th', text: 'Check the twin first.' })
  })

  it('ends a turn on an interrupt, collects the decision, and resumes with it', () => {
    const waiting = run(initialChatState, ...interruptRun)
    expect(waiting.interrupts.map(item => item.id)).toEqual(['int-c1'])
    expect(tool(waiting, 'c1').status).toBe('awaiting')
    expect(allDecided(waiting)).toBe(false)
    const decided = apply(waiting, { type: 'decide', interruptId: 'int-c1', decision: { approved: false, reason: 'Not yet' } })
    expect(tool(decided, 'c1')).toMatchObject({ status: 'denied', reason: 'Not yet' })
    expect(allDecided(decided)).toBe(true)
    expect(resumeEntries(decided)).toEqual([{ interruptId: 'int-c1', status: 'resolved', payload: { approved: false, reason: 'Not yet' } }])
    const approved = apply(waiting, { type: 'decide', interruptId: 'int-c1', decision: { approved: true } })
    expect(resumeEntries(approved)[0].payload).toEqual({ approved: true })
    const resumed = run(approved,
      { type: 'RUN_STARTED', threadId: 't', runId: 'r2' },
      { type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'x', content: '{"id": 9, "name": "Karl"}' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 'Karl is in the cast.' },
      { type: 'RUN_FINISHED', threadId: 't', runId: 'r2', outcome: { type: 'success' } })
    expect(tool(resumed, 'c1')).toMatchObject({ status: 'done', result: '{"id": 9, "name": "Karl"}' })
    expect(resumed.interrupts).toEqual([])
    expect(resumed.entries.at(-1)).toEqual({ kind: 'text', id: 'm2', text: 'Karl is in the cast.' })
  })

  it('ignores decisions for unknown interrupts', () => {
    const waiting = run(initialChatState, ...interruptRun)
    expect(apply(waiting, { type: 'decide', interruptId: 'nope', decision: { approved: true } })).toBe(waiting)
  })

  it('records RUN_ERROR, a failed transport and a stop', () => {
    const failed = run(initialChatState, { type: 'RUN_STARTED', threadId: 't', runId: 'r' }, { type: 'RUN_ERROR', message: 'Model provider unavailable' })
    expect(failed).toMatchObject({ status: 'error', error: 'Model provider unavailable' })
    expect(run(failed, { type: 'RUN_STARTED', threadId: 't', runId: 'r2' }).error).toBeUndefined()
    expect(apply(initialChatState, { type: 'failed', message: 'Temporal is unavailable' })).toMatchObject({ status: 'error', error: 'Temporal is unavailable' })
    expect(apply(initialChatState, { type: 'stopped' }).status).toBe('stopped')
  })

  it('finds studio-side calls of the last run and builds their result messages', () => {
    const state = run(initialChatState,
      { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
      { type: 'TOOL_CALL_START', toolCallId: 'n1', toolCallName: 'navigate', parentMessageId: 'a1' },
      { type: 'TOOL_CALL_ARGS', toolCallId: 'n1', delta: '{"path": "/projects/3/outline"}' },
      { type: 'TOOL_CALL_END', toolCallId: 'n1' },
      { type: 'TOOL_CALL_START', toolCallId: 'b1', toolCallName: 'read_outline', parentMessageId: 'a1' },
      { type: 'TOOL_CALL_END', toolCallId: 'b1' },
      { type: 'RUN_FINISHED', threadId: 't', runId: 'r1', outcome: { type: 'success' } })
    const calls = pendingFrontendCalls(state, new Set(['navigate', 'open_scene']))
    expect(calls.map(call => call.id)).toEqual(['n1'])
    expect(toolResultMessages(calls, { n1: 'Opened /projects/3/outline' })).toEqual([
      { id: 'a1', role: 'assistant', toolCalls: [{ id: 'n1', type: 'function', function: { name: 'navigate', arguments: '{"path": "/projects/3/outline"}' } }] },
      { id: 'result-n1', role: 'tool', toolCallId: 'n1', content: 'Opened /projects/3/outline' },
    ])
    const answered = apply(state, { type: 'tool-result', toolCallId: 'n1', content: 'Opened' })
    expect(pendingFrontendCalls(answered, new Set(['navigate']))).toEqual([])
  })

  it('rebuilds a stored thread from AG-UI messages', () => {
    const entries = entriesFromMessages([
      { id: 'm1', role: 'user', content: 'Show me the outline' },
      { id: 'a1', role: 'assistant', toolCalls: [{ id: 'n1', type: 'function', function: { name: 'navigate', arguments: '{"path": "/projects/1/outline"}' } }] },
      { id: 't1', role: 'tool', toolCallId: 'n1', content: 'Navigated' },
      { id: 'a2', role: 'assistant', content: 'Here is the outline.' },
    ])
    expect(entries).toEqual([
      { kind: 'user', id: 'm1', text: 'Show me the outline' },
      { kind: 'tool', id: 'n1', name: 'navigate', args: '{"path": "/projects/1/outline"}', parentId: 'a1', status: 'done', result: 'Navigated' },
      { kind: 'text', id: 'a2', text: 'Here is the outline.' },
    ])
    expect(apply(initialChatState, { type: 'load', messages: [{ id: 'm1', role: 'user', content: 'Hi' }] }).entries).toHaveLength(1)
  })
})
