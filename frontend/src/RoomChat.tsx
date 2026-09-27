import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { AgentRole, CLIENT_ID, getAgentRoles } from './api'

const TOOL_LABELS: Record<string, string> = {
  read_project_overview: 'Read the project overview',
  read_story_twin: 'Checked the Story twin',
  read_screenplay_scenes: 'Read scenes',
  retrieve_project_context: 'Searched the project',
  read_project_artifacts: 'Read the story artifacts',
  consult: 'Consulted a specialist',
  propose_screenplay_change: 'Proposed a script change',
  start_room_workflow: 'Started a room workflow',
}

type Part = UIMessage['parts'][number]

/** Return the tool name and state of a tool-call part, or null for other parts. */
function toolCall(part: Part): { name: string; state: string; input: unknown } | null {
  if (part.type === 'dynamic-tool') return { name: part.toolName, state: part.state, input: part.input }
  if (part.type.startsWith('tool-')) {
    const tool = part as { type: string; state: string; input?: unknown }
    return { name: tool.type.slice(5), state: tool.state, input: tool.input }
  }
  return null
}

function ToolChip({ name, state, input }: { name: string; state: string; input: unknown }) {
  const done = state === 'output-available'
  const failed = state === 'output-error'
  const role = name === 'consult' && input && typeof input === 'object' && 'role' in input ? ` (${String((input as { role: unknown }).role).replace(/_/g, ' ')})` : ''
  return <span className={`tool-chip ${done ? 'done' : failed ? 'failed' : 'working'}`}>{TOOL_LABELS[name] ?? name.replace(/_/g, ' ')}{role}{done ? ' ✓' : failed ? ' ✗' : '…'}</span>
}

/** Talk to one room role; replies stream in with the tools the agent uses shown as they happen. */
export default function RoomChat({ projectId, sceneId = null }: { projectId: number; sceneId?: number | null }) {
  const [roles, setRoles] = useState<AgentRole[]>([])
  const [role, setRole] = useState('showrunner')
  const [mode, setMode] = useState<'chat_only' | 'suggest'>('chat_only')
  const [draft, setDraft] = useState('')
  const settings = useRef({ role, mode })
  settings.current = { role, mode }
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { getAgentRoles().then(setRoles).catch(() => undefined) }, [])

  const transport = useMemo(() => new DefaultChatTransport({
    api: `/api/v1/projects/${projectId}/room/chat`,
    credentials: 'same-origin',
    headers: { 'X-DraftPilot-Client': CLIENT_ID },
    prepareSendMessagesRequest: ({ messages, id, trigger, messageId }) => {
      const query = new URLSearchParams({ role: settings.current.role, permission_mode: settings.current.mode, page: 'room' })
      if (sceneId) query.set('scene_id', String(sceneId))
      return { api: `/api/v1/projects/${projectId}/room/chat?${query}`, body: { id, messages, trigger, messageId } }
    },
  }), [projectId, sceneId])
  const { messages, sendMessage, status, error, stop } = useChat({ id: `room-${projectId}`, transport })
  const busy = status === 'submitted' || status === 'streaming'

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end' }) }, [messages])

  function send(event: FormEvent): void {
    event.preventDefault()
    if (!draft.trim() || busy) return
    void sendMessage({ text: draft.trim() })
    setDraft('')
  }

  return <section className="room-chat" aria-label="Room chat">
    <div className="room-chat-head"><p className="eyebrow warm">TALK TO THE ROOM</p>
      <label>Who<select aria-label="Room role" value={role} onChange={event => setRole(event.target.value)}>{(roles.length ? roles : [{ key: 'showrunner', label: 'Showrunner' } as AgentRole]).map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      <label>May<select aria-label="Chat permission" value={mode} onChange={event => setMode(event.target.value as 'chat_only' | 'suggest')}><option value="chat_only">Only advise</option><option value="suggest">Propose changes</option></select></label>
    </div>
    <div className="room-chat-log" aria-live="polite">
      {messages.length === 0 && <p className="empty-copy">Ask the {roles.find(item => item.key === role)?.label.toLowerCase() ?? 'room'} anything about your project. The showrunner brings in specialists when it needs them.</p>}
      {messages.map(message => <article key={message.id} className={`room-message ${message.role}`}>
        {message.parts.map((part, index) => {
          const tool = toolCall(part)
          if (tool) return <ToolChip key={index} {...tool} />
          if (part.type === 'reasoning') return <details key={index} className="reasoning"><summary>Thinking</summary><p>{part.text}</p></details>
          if (part.type === 'text') return <p key={index} className="message-text">{part.text}</p>
          return null
        })}
      </article>)}
      {status === 'submitted' && <p className="room-typing">The room is reading your project…</p>}
      {error && <p className="error-text" role="alert">{error.message || 'The room could not answer.'}</p>}
      <div ref={endRef} />
    </div>
    <form className="room-chat-compose" onSubmit={send}><textarea aria-label="Message the room" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) send(event) }} placeholder="What does Will want from Edward?" rows={2} />{busy ? <button className="button quiet" type="button" onClick={() => void stop()}>Stop</button> : <button className="button primary" type="submit" disabled={!draft.trim()}>Send</button>}</form>
  </section>
}
