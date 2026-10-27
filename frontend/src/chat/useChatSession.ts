import { useCallback, useEffect, useRef, useState } from 'react'
import type { Message, RunAgentInput, Tool } from '@ag-ui/core'
import { ApiError } from '../api'
import { chatApi, newId } from './api'
import {
  allDecided, type ChatAction, chatReducer, type ChatState, type Decision, initialChatState,
  pendingFrontendCalls, resumeEntries, type ToolEntry, toolResultMessages,
} from './reducer'
import { streamRun } from './transport'

export type SessionOptions = {
  /** `forwardedProps` for the next run: role, mode, provider profile and the writer's focus. */
  props: () => Record<string, unknown>
  /** Studio-side tools the agent may call. */
  tools: Tool[]
  /** Run one studio-side tool call and return its result text. */
  runTool: (call: ToolEntry) => Promise<string>
  /** Called after every run (e.g. to refresh the thread list). */
  onSettled?: () => void
}

const threadKey = (projectId: number) => `draftpilot:chat-thread:${projectId}`

function storedThread(projectId: number): string | null {
  try { return window.localStorage.getItem(threadKey(projectId)) } catch { return null }
}

function rememberThread(projectId: number, threadId: string): void {
  try { window.localStorage.setItem(threadKey(projectId), threadId) } catch { /* private mode */ }
}

const messageOf = (reason: unknown) => (reason instanceof Error ? reason.message : 'The room could not answer.')

/** One project's chat: the conversation state, its thread, and the run loop (send, approve, studio tools, stop, retry). */
export function useChatSession(projectId: number, options: SessionOptions) {
  const [state, setState] = useState<ChatState>(initialChatState)
  const stateRef = useRef(state)
  const [threadId, setThreadIdState] = useState(() => storedThread(projectId) ?? newId())
  const threadRef = useRef(threadId)
  const abortRef = useRef<AbortController | null>(null)
  const lastInput = useRef<RunAgentInput | null>(null)
  const optionsRef = useRef(options)
  optionsRef.current = options

  const dispatch = useCallback((action: ChatAction) => {
    stateRef.current = chatReducer(stateRef.current, action)
    setState(stateRef.current)
  }, [])

  const setThread = useCallback((id: string) => {
    threadRef.current = id
    setThreadIdState(id)
    rememberThread(projectId, id)
  }, [projectId])

  const buildInput = useCallback((messages: Message[], resume?: RunAgentInput['resume']): RunAgentInput => ({
    threadId: threadRef.current,
    runId: newId(),
    state: {},
    messages,
    tools: optionsRef.current.tools,
    context: [],
    forwardedProps: optionsRef.current.props(),
    ...(resume ? { resume } : {}),
  }), [])

  const run = useCallback(async (input: RunAgentInput): Promise<void> => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    lastInput.current = input
    rememberThread(projectId, input.threadId)
    try {
      await streamRun(chatApi.url(projectId), input, event => dispatch({ type: 'event', event }), controller.signal)
    } catch (reason) {
      dispatch({ type: 'failed', message: messageOf(reason) })
      return
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      optionsRef.current.onSettled?.()
    }
    if (controller.signal.aborted) { dispatch({ type: 'stopped' }); return }
    if (stateRef.current.status === 'running') dispatch({ type: 'event', event: { type: 'RUN_FINISHED' } })
    const current = stateRef.current
    const names = new Set(optionsRef.current.tools.map(tool => tool.name))
    const calls = current.status === 'idle' && current.interrupts.length === 0 ? pendingFrontendCalls(current, names) : []
    if (!calls.length) return
    const results: Record<string, string> = {}
    for (const call of calls) {
      try { results[call.id] = await optionsRef.current.runTool(call) } catch (reason) { results[call.id] = `Failed: ${messageOf(reason)}` }
      dispatch({ type: 'tool-result', toolCallId: call.id, content: results[call.id] })
    }
    await run(buildInput(toolResultMessages(calls, results)))
  }, [buildInput, dispatch, projectId])

  const send = useCallback((text: string) => {
    const message = text.trim()
    if (!message || stateRef.current.status === 'running') return
    const id = newId()
    dispatch({ type: 'user', id, text: message })
    void run(buildInput([{ id, role: 'user', content: message }]))
  }, [buildInput, dispatch, run])

  const decide = useCallback((interruptId: string, decision: Decision) => {
    dispatch({ type: 'decide', interruptId, decision })
    if (allDecided(stateRef.current)) {
      const resume = resumeEntries(stateRef.current)
      dispatch({ type: 'event', event: { type: 'RUN_STARTED', runId: '' } })
      void run(buildInput([], resume))
    }
  }, [buildInput, dispatch, run])

  const stop = useCallback(() => { abortRef.current?.abort() }, [])

  const retry = useCallback(() => {
    if (lastInput.current) void run({ ...lastInput.current, runId: newId(), forwardedProps: optionsRef.current.props() })
  }, [run])

  const regenerate = useCallback(() => {
    const last = [...stateRef.current.entries].reverse().find(entry => entry.kind === 'user')
    if (last && last.kind === 'user') send(last.text)
  }, [send])

  const newThread = useCallback(() => {
    abortRef.current?.abort()
    lastInput.current = null
    setThread(newId())
    dispatch({ type: 'reset' })
  }, [dispatch, setThread])

  const openThread = useCallback(async (id: string) => {
    abortRef.current?.abort()
    lastInput.current = null
    setThread(id)
    dispatch({ type: 'reset' })
    try {
      const thread = await chatApi.thread(projectId, id)
      if (threadRef.current === id) dispatch({ type: 'load', messages: Array.isArray(thread?.messages) ? thread.messages : [] })
    } catch (reason) {
      // A thread that never finished a turn isn't stored yet: keep its id and start empty.
      if (!(reason instanceof ApiError && reason.status === 404)) dispatch({ type: 'failed', message: messageOf(reason) })
    }
  }, [dispatch, projectId, setThread])

  // Reopen the project's last thread once, then stop any stream when the dock goes away.
  useEffect(() => {
    void openThread(threadRef.current)
    return () => abortRef.current?.abort()
  }, [openThread])

  return { state, threadId, send, decide, stop, retry, regenerate, newThread, openThread }
}
