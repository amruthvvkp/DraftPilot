import type { Interrupt, Message } from '@ag-ui/core'

/** A tool call's life: arguments streaming, called, waiting for the writer, decided, finished. */
export type ToolStatus = 'streaming' | 'called' | 'awaiting' | 'approved' | 'denied' | 'done'

export type UserEntry = { kind: 'user'; id: string; text: string }
export type TextEntry = { kind: 'text'; id: string; text: string }
export type ReasoningEntry = { kind: 'reasoning'; id: string; text: string }
export type ToolEntry = {
  kind: 'tool'; id: string; name: string; args: string; parentId?: string
  result?: string; status: ToolStatus; reason?: string; runId?: string
}
export type Entry = UserEntry | TextEntry | ReasoningEntry | ToolEntry

export type Decision = { approved: boolean; reason?: string }
export type ChatStatus = 'idle' | 'running' | 'error' | 'stopped'

export type ChatState = {
  entries: Entry[]
  status: ChatStatus
  runId?: string
  error?: string
  /** Interrupts the last run ended with, and the writer's answers so far. */
  interrupts: Interrupt[]
  decisions: Record<string, Decision>
}

/** An AG-UI event as it arrives on the wire (camelCase fields, `type` as a string). */
export type ChatEvent = { type: string; [field: string]: unknown }

export type ChatAction =
  | { type: 'event'; event: ChatEvent }
  | { type: 'user'; id: string; text: string }
  | { type: 'load'; messages: Message[] }
  | { type: 'reset' }
  | { type: 'stopped' }
  | { type: 'failed'; message: string }
  | { type: 'decide'; interruptId: string; decision: Decision }
  | { type: 'tool-result'; toolCallId: string; content: string }

export const initialChatState: ChatState = { entries: [], status: 'idle', interrupts: [], decisions: {} }

const str = (value: unknown): string => (typeof value === 'string' ? value : '')

function upsertText(entries: Entry[], kind: 'text' | 'reasoning', id: string, delta: string): Entry[] {
  const index = entries.findIndex(entry => entry.kind === kind && entry.id === id)
  if (index < 0) return [...entries, { kind, id, text: delta }]
  const entry = entries[index] as TextEntry | ReasoningEntry
  return entries.map((item, at) => (at === index ? { ...entry, text: entry.text + delta } : item))
}

function updateTool(entries: Entry[], id: string, change: (entry: ToolEntry) => ToolEntry): Entry[] {
  return entries.map(entry => (entry.kind === 'tool' && entry.id === id ? change(entry) : entry))
}

function startTool(state: ChatState, id: string, name: string, parentId?: string): Entry[] {
  if (state.entries.some(entry => entry.kind === 'tool' && entry.id === id)) return state.entries
  return [...state.entries, { kind: 'tool', id, name, args: '', parentId, status: 'streaming', runId: state.runId }]
}

/** Fold one AG-UI event into the conversation. */
function applyEvent(state: ChatState, event: ChatEvent): ChatState {
  const messageId = str(event.messageId)
  const toolCallId = str(event.toolCallId)
  switch (event.type) {
    case 'RUN_STARTED':
      return { ...state, status: 'running', runId: str(event.runId), error: undefined, interrupts: [], decisions: {} }
    case 'TEXT_MESSAGE_START':
      return state
    case 'TEXT_MESSAGE_CONTENT':
    case 'TEXT_MESSAGE_CHUNK':
      return str(event.delta) ? { ...state, entries: upsertText(state.entries, 'text', messageId || `text-${state.runId}`, str(event.delta)) } : state
    case 'REASONING_MESSAGE_CONTENT':
    case 'REASONING_MESSAGE_CHUNK':
      return str(event.delta) ? { ...state, entries: upsertText(state.entries, 'reasoning', messageId || `reasoning-${state.runId}`, str(event.delta)) } : state
    case 'TOOL_CALL_START':
      return { ...state, entries: startTool(state, toolCallId, str(event.toolCallName), str(event.parentMessageId) || undefined) }
    case 'TOOL_CALL_CHUNK': {
      const entries = str(event.toolCallName) ? startTool(state, toolCallId, str(event.toolCallName), str(event.parentMessageId) || undefined) : state.entries
      return { ...state, entries: updateTool(entries, toolCallId, entry => ({ ...entry, args: entry.args + str(event.delta) })) }
    }
    case 'TOOL_CALL_ARGS':
      return { ...state, entries: updateTool(state.entries, toolCallId, entry => ({ ...entry, args: entry.args + str(event.delta) })) }
    case 'TOOL_CALL_END':
      return { ...state, entries: updateTool(state.entries, toolCallId, entry => ({ ...entry, status: entry.status === 'streaming' ? 'called' : entry.status })) }
    case 'TOOL_CALL_RESULT':
      return { ...state, entries: updateTool(state.entries, toolCallId, entry => ({ ...entry, result: str(event.content), status: 'done' })) }
    case 'RUN_ERROR':
      return { ...state, status: 'error', error: str(event.message) || 'The room could not answer.' }
    case 'RUN_FINISHED': {
      const outcome = event.outcome as { type?: string; interrupts?: Interrupt[] } | undefined
      const interrupts = outcome?.type === 'interrupt' ? outcome.interrupts ?? [] : []
      const waiting = new Set(interrupts.map(item => item.toolCallId).filter(Boolean))
      const entries = waiting.size ? state.entries.map(entry => (entry.kind === 'tool' && waiting.has(entry.id) ? { ...entry, status: 'awaiting' as const } : entry)) : state.entries
      return { ...state, status: 'idle', entries, interrupts, decisions: {} }
    }
    default:
      return state
  }
}

/** Rebuild the conversation from stored AG-UI messages (reopening a thread). */
export function entriesFromMessages(messages: Message[]): Entry[] {
  const entries: Entry[] = []
  const tools = new Map<string, ToolEntry>()
  for (const message of messages) {
    const content = typeof message.content === 'string' ? message.content : ''
    if (message.role === 'user') entries.push({ kind: 'user', id: message.id, text: content })
    else if (message.role === 'reasoning') entries.push({ kind: 'reasoning', id: message.id, text: content })
    else if (message.role === 'assistant') {
      if (content) entries.push({ kind: 'text', id: message.id, text: content })
      for (const call of message.toolCalls ?? []) {
        const entry: ToolEntry = { kind: 'tool', id: call.id, name: call.function.name, args: call.function.arguments, parentId: message.id, status: 'called' }
        tools.set(call.id, entry)
        entries.push(entry)
      }
    } else if (message.role === 'tool') {
      const entry = tools.get(message.toolCallId)
      if (entry) Object.assign(entry, { result: content, status: 'done' })
    }
  }
  return entries
}

/** The pure chat reducer: AG-UI events plus the writer's own actions. */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'event':
      return applyEvent(state, action.event)
    case 'user':
      return { ...state, status: 'running', error: undefined, entries: [...state.entries, { kind: 'user', id: action.id, text: action.text }] }
    case 'load':
      return { ...initialChatState, entries: entriesFromMessages(action.messages) }
    case 'reset':
      return initialChatState
    case 'stopped':
      return { ...state, status: 'stopped' }
    case 'failed':
      return { ...state, status: 'error', error: action.message }
    case 'decide': {
      const interrupt = state.interrupts.find(item => item.id === action.interruptId)
      if (!interrupt) return state
      const status: ToolStatus = action.decision.approved ? 'approved' : 'denied'
      const entries = interrupt.toolCallId ? updateTool(state.entries, interrupt.toolCallId, entry => ({ ...entry, status, reason: action.decision.reason })) : state.entries
      return { ...state, entries, decisions: { ...state.decisions, [action.interruptId]: action.decision } }
    }
    case 'tool-result':
      return { ...state, entries: updateTool(state.entries, action.toolCallId, entry => ({ ...entry, result: action.content, status: 'done' })) }
  }
}

/** Whether every interrupt of the last run has the writer's answer. */
export function allDecided(state: ChatState): boolean {
  return state.interrupts.length > 0 && state.interrupts.every(item => item.id in state.decisions)
}

/** The AG-UI resume entries answering the last run's interrupts. */
export function resumeEntries(state: ChatState) {
  return state.interrupts.map(item => {
    const decision = state.decisions[item.id]
    return { interruptId: item.id, status: 'resolved' as const, payload: decision?.reason ? { approved: decision.approved, reason: decision.reason } : { approved: Boolean(decision?.approved) } }
  })
}

/** Calls to studio-side tools from the last run that the studio has not answered yet. */
export function pendingFrontendCalls(state: ChatState, names: ReadonlySet<string>): ToolEntry[] {
  return state.entries.filter((entry): entry is ToolEntry =>
    entry.kind === 'tool' && names.has(entry.name) && entry.status === 'called' && entry.result === undefined && entry.runId === state.runId)
}

/** The messages that hand studio-side tool results back to the agent: the assistant's calls, then each result. */
export function toolResultMessages(calls: ToolEntry[], results: Record<string, string>): Message[] {
  if (!calls.length) return []
  const assistant: Message = {
    id: calls[0].parentId ?? `assistant-${calls[0].id}`,
    role: 'assistant',
    toolCalls: calls.map(call => ({ id: call.id, type: 'function', function: { name: call.name, arguments: call.args || '{}' } })),
  }
  return [assistant, ...calls.map(call => ({ id: `result-${call.id}`, role: 'tool' as const, toolCallId: call.id, content: results[call.id] ?? '' }))]
}

/** Parse a JSON string, or return it unchanged when it isn't JSON. */
export function parseJson(text: string | undefined): unknown {
  if (text === undefined || text === '') return undefined
  try { return JSON.parse(text) } catch { return text }
}
