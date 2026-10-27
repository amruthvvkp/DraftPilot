import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { type Call, mockApi, renderAt, sse, workspace } from '../test/harness'

type Body = { threadId: string; messages: { role: string; content?: string; toolCalls?: unknown[]; toolCallId?: string }[]; tools: { name: string }[]; forwardedProps: Record<string, unknown>; resume?: unknown[] }

const scene = { id: 7, act_id: 4, heading: 'INT. HALL - NIGHT', position: 0, body: '', version: 1, scene_instruction: '' }
const studio = {
  'GET /api/v1/projects/3/workspace': workspace(3, { scenes: [scene], blocks: { 7: [] } }),
  'GET /api/v1/projects/3/storyline': { project_id: 3, version: 1, title: 'Lantern House' },
  'GET /api/v1/projects/3/characters': [],
  'GET /api/v1/projects/3/beats': [],
  'GET /api/v1/projects/3/agent-proposals': [],
  'GET /api/v1/projects/3/room/threads': [],
  'GET /api/v1/agents/roles': [{ key: 'showrunner', label: 'Showrunner', description: '', default_permission: 'suggest' }, { key: 'story_architect', label: 'Story architect', description: '', default_permission: 'suggest' }],
  'GET /api/v1/settings/providers': [],
}

const reply = (runId: string, text: string) => [
  { type: 'RUN_STARTED', threadId: 't', runId },
  { type: 'TEXT_MESSAGE_START', messageId: `m-${runId}`, role: 'assistant' },
  { type: 'TEXT_MESSAGE_CONTENT', messageId: `m-${runId}`, delta: text },
  { type: 'TEXT_MESSAGE_END', messageId: `m-${runId}` },
  { type: 'RUN_FINISHED', threadId: 't', runId, outcome: { type: 'success' } },
]

/** Serve the chat endpoint from a script of turns, recording each request body. */
function chatBackend(turns: ((body: Body) => object[])[], extra: Record<string, unknown> = {}) {
  const bodies: Body[] = []
  const api = mockApi({
    ...studio,
    ...extra,
    'POST /api/v1/projects/3/room/chat': (call: Call) => {
      const body = call.body as Body
      bodies.push(body)
      const turn = turns[bodies.length - 1]
      return turn ? sse(turn(body)) : new Response(JSON.stringify({ detail: 'No more turns' }), { status: 500 })
    },
  } as Parameters<typeof mockApi>[0])
  return { api, bodies }
}

async function ask(text: string) {
  const box = await screen.findByLabelText('Message the room')
  await userEvent.type(box, text)
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
}

beforeEach(() => { window.localStorage.clear(); window.localStorage.setItem('draftpilot:chat-dock', 'open') })

describe('ChatDock', () => {
  it('streams a Markdown reply and sends the page context', async () => {
    const { bodies } = chatBackend([() => reply('r1', 'Open on **the river**.')])
    renderAt('/projects/3')
    await screen.findByDisplayValue('INT. HALL - NIGHT')
    await screen.findByRole('option', { name: 'Story architect' })
    await userEvent.selectOptions(screen.getByLabelText('Room role'), 'story_architect')
    await ask('Where should we open?')
    const log = screen.getByRole('log', { name: 'Conversation' })
    expect((await within(log).findByText('the river')).tagName).toBe('STRONG')
    const body = bodies[0]
    expect(body.messages).toEqual([expect.objectContaining({ role: 'user', content: 'Where should we open?' })])
    expect(body.forwardedProps).toMatchObject({ role: 'story_architect', permission_mode: 'suggest', page: '/projects/3', artifact: 'screenplay', selection: 'INT. HALL - NIGHT', scene_id: 7 })
    expect(body.tools.map(tool => tool.name)).toEqual(['navigate', 'open_scene'])
    expect(window.localStorage.getItem('draftpilot:chat-thread:3')).toBe(body.threadId)
  })

  it('asks for approval on an interrupt, then resumes the same thread', async () => {
    const { bodies } = chatBackend([
      () => [
        { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
        { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'create_story_entity', parentMessageId: 'a1' },
        { type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{"project_id": 3, "kind": "character", "fields": {"name": "Karl"}}' },
        { type: 'TOOL_CALL_END', toolCallId: 'c1' },
        { type: 'RUN_FINISHED', threadId: 't', runId: 'r1', outcome: { type: 'interrupt', interrupts: [{ id: 'int-c1', reason: 'tool_call', toolCallId: 'c1', message: 'Approve?' }] } },
      ],
      () => [
        { type: 'RUN_STARTED', threadId: 't', runId: 'r2' },
        { type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'x', content: '{"id": 9, "name": "Karl", "role": "supporting"}' },
        ...reply('r2', 'Karl is in the cast.').slice(1),
      ],
    ])
    renderAt('/projects/3/characters')
    await userEvent.selectOptions(await screen.findByLabelText('Chat permission'), 'project_edit')
    await ask('Add Karl the giant.')
    const card = await screen.findByRole('region', { name: 'Approve create_story_entity' })
    expect(card.textContent).toContain('"name": "Karl"')
    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))
    expect(await screen.findByText('Karl is in the cast.')).toBeTruthy()
    expect(screen.getByText('New character: Karl')).toBeTruthy()
    expect(bodies[1]).toMatchObject({ threadId: bodies[0].threadId, messages: [], resume: [{ interruptId: 'int-c1', status: 'resolved', payload: { approved: true } }] })
    expect(bodies[1].forwardedProps.permission_mode).toBe('project_edit')
  })

  it('runs a studio tool the agent calls and hands the result back', async () => {
    const { bodies } = chatBackend([
      () => [
        { type: 'RUN_STARTED', threadId: 't', runId: 'r1' },
        { type: 'TOOL_CALL_START', toolCallId: 'n1', toolCallName: 'navigate', parentMessageId: 'a1' },
        { type: 'TOOL_CALL_ARGS', toolCallId: 'n1', delta: '{"path": "/projects/3/outline"}' },
        { type: 'TOOL_CALL_END', toolCallId: 'n1' },
        { type: 'RUN_FINISHED', threadId: 't', runId: 'r1', outcome: { type: 'success' } },
      ],
      () => reply('r2', 'Here is the outline.'),
    ])
    renderAt('/projects/3/storyline')
    await ask('Show me the outline')
    expect(await screen.findByText('Here is the outline.')).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Outline' })).toBeTruthy()
    expect(bodies[1].messages).toEqual([
      { id: 'a1', role: 'assistant', toolCalls: [{ id: 'n1', type: 'function', function: { name: 'navigate', arguments: '{"path": "/projects/3/outline"}' } }] },
      { id: 'result-n1', role: 'tool', toolCallId: 'n1', content: 'Opened /projects/3/outline' },
    ])
  })

  it('shows a run error with retry, and reopens a stored thread', async () => {
    const { bodies } = chatBackend([
      () => [{ type: 'RUN_STARTED', threadId: 't', runId: 'r1' }, { type: 'RUN_ERROR', message: 'Model provider unavailable' }],
      () => reply('r2', 'Back again.'),
    ], {
      'GET /api/v1/projects/3/room/threads': [{ id: 'old', project_id: 3, title: 'Opening scene', role: 'showrunner', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' }],
      'GET /api/v1/projects/3/room/threads/old': { id: 'old', title: 'Opening scene', messages: [{ id: 'u', role: 'user', content: 'Where do we open?' }, { id: 'a', role: 'assistant', content: 'On the river.' }] },
    })
    renderAt('/projects/3/outline')
    await ask('Hello')
    expect((await screen.findByRole('alert')).textContent).toContain('Model provider unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Back again.')).toBeTruthy()
    expect(bodies[1].threadId).toBe(bodies[0].threadId)

    await userEvent.click(screen.getByRole('button', { name: 'Conversations' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Open Opening scene' }))
    expect(await screen.findByText('On the river.')).toBeTruthy()
    expect(screen.queryByText('Back again.')).toBeNull()
    await waitFor(() => expect(window.localStorage.getItem('draftpilot:chat-thread:3')).toBe('old'))
  })

  it('collapses and stays collapsed', async () => {
    chatBackend([])
    renderAt('/projects/3/outline')
    await userEvent.click(await screen.findByRole('button', { name: 'Collapse chat' }))
    expect(screen.queryByLabelText('Message the room')).toBeNull()
    expect(window.localStorage.getItem('draftpilot:chat-dock')).toBe('closed')
    await userEvent.click(screen.getByRole('button', { name: '✦ Chat' }))
    expect(await screen.findByLabelText('Message the room')).toBeTruthy()
  })

  it('starts collapsed on a narrow screen until the writer opens it', async () => {
    window.localStorage.clear()
    window.innerWidth = 1024
    chatBackend([])
    renderAt('/projects/3/outline')
    expect(await screen.findByRole('button', { name: '✦ Chat' })).toBeTruthy()
    expect(screen.queryByLabelText('Message the room')).toBeNull()
  })
})
