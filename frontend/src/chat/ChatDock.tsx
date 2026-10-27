import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Tool } from '@ag-ui/core'
import { getAgentRoles, listProviderProfiles } from '../api'
import { keys } from '../data/queries'
import { CHAT_MODES, type ChatMode } from './api'
import { DOCK_KEY, readDockOpen } from './dockState'
import { useCurrentFocus } from './focus'
import { roleLabel } from './labels'
import MessageList from './MessageList'
import PendingProposals from './PendingProposals'
import type { ToolEntry } from './reducer'
import { argsOf } from './registry'
import ThreadList from './ThreadList'
import { useChatSession } from './useChatSession'
import './chat.css'

/** Tools the studio runs itself: the agent can move the writer around the studio. */
export const FRONTEND_TOOLS: Tool[] = [
  {
    name: 'navigate',
    description: 'Open a studio page for the writer. `path` is a studio path for this project, e.g. /projects/<id>/storyline, '
      + '/characters, /characters/<character_id>, /locations, /outline, /context-map, /twin, /room, or /projects/<id> for the script.',
    parameters: { type: 'object', properties: { path: { type: 'string', description: 'Studio path starting with /projects/' } }, required: ['path'] },
  },
  {
    name: 'open_scene',
    description: 'Open a scene of this project in the script editor.',
    parameters: { type: 'object', properties: { scene_id: { type: 'integer', description: 'The scene id' } }, required: ['scene_id'] },
  },
]

/** The persistent chat dock: one AG-UI conversation with the room, on every project page. */
export default function ChatDock({ projectId }: { projectId: number }) {
  const navigate = useNavigate()
  const location = useLocation()
  const focus = useCurrentFocus()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(readDockOpen)
  const [role, setRole] = useState('showrunner')
  const [mode, setMode] = useState<ChatMode>('suggest')
  const [profile, setProfile] = useState('')
  const [draft, setDraft] = useState('')
  const [threadsOpen, setThreadsOpen] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const roles = useQuery({ queryKey: ['agent-roles'], queryFn: getAgentRoles, staleTime: Infinity }).data ?? []
  const profiles = (useQuery({ queryKey: ['provider-profiles'], queryFn: listProviderProfiles, staleTime: 60_000 }).data ?? []).filter(item => item.enabled)

  async function runTool(call: ToolEntry): Promise<string> {
    const args = argsOf(call)
    if (call.name === 'open_scene') {
      const sceneId = Number(args.scene_id)
      if (!Number.isInteger(sceneId) || sceneId <= 0) return 'Failed: scene_id must be a scene id'
      navigate(`/projects/${projectId}?scene=${sceneId}`)
      return `Opened scene ${sceneId} in the script editor`
    }
    const path = typeof args.path === 'string' ? args.path.trim() : ''
    if (!/^\/projects(\/|$)/.test(path) && path !== '/settings') return 'Failed: only studio paths under /projects can be opened'
    navigate(path)
    return `Opened ${path}`
  }

  const session = useChatSession(projectId, {
    tools: FRONTEND_TOOLS,
    runTool,
    props: () => ({
      role, permission_mode: mode, provider_profile_id: profile ? Number(profile) : null,
      page: location.pathname, artifact: focus.artifact ?? null, selection: focus.selection ?? null, scene_id: focus.scene_id ?? null,
    }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: keys.threads(projectId) })
      void queryClient.invalidateQueries({ queryKey: keys.proposals(projectId) })
    },
  })
  const { state } = session
  const busy = state.status === 'running'

  // Keep the newest message in view by scrolling the log itself (never the page under it).
  useEffect(() => { const log = logRef.current; if (log) log.scrollTop = log.scrollHeight }, [state.entries])

  function toggle(next: boolean): void {
    setOpen(next)
    try { window.localStorage.setItem(DOCK_KEY, next ? 'open' : 'closed') } catch { /* private mode */ }
  }

  function send(event?: FormEvent): void {
    event?.preventDefault()
    if (!draft.trim() || busy) return
    session.send(draft)
    setDraft('')
  }

  if (!open) return <aside className="chat-dock collapsed" aria-label="Chat">
    <button type="button" className="chat-dock-toggle" aria-expanded="false" onClick={() => toggle(true)}>✦ Chat</button>
  </aside>

  const lastIsAnswer = state.entries.length > 0 && state.entries[state.entries.length - 1].kind !== 'user'
  return <aside className="chat-dock" aria-label="Chat">
    <header className="chat-dock-head">
      <p className="eyebrow warm">TALK TO THE ROOM</p>
      <button type="button" className="mini-button" aria-expanded={threadsOpen} onClick={() => setThreadsOpen(value => !value)}>Conversations</button>
      <button type="button" className="mini-button" onClick={() => { session.newThread(); setThreadsOpen(false) }}>New</button>
      <button type="button" className="mini-button" aria-label="Collapse chat" aria-expanded="true" onClick={() => toggle(false)}>⟩</button>
    </header>
    {threadsOpen && <ThreadList projectId={projectId} currentId={session.threadId} onNew={() => { session.newThread(); setThreadsOpen(false) }}
      onOpen={id => { void session.openThread(id); setThreadsOpen(false) }} />}
    <div className="chat-dock-controls">
      <label>Who<select aria-label="Room role" value={role} onChange={event => setRole(event.target.value)}>
        {(roles.length ? roles : [{ key: 'showrunner', label: 'Showrunner' }]).map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
      </select></label>
      <label>May<select aria-label="Chat permission" value={mode} onChange={event => setMode(event.target.value as ChatMode)}>
        {CHAT_MODES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select></label>
      {profiles.length > 0 && <label>Model<select aria-label="Provider profile" value={profile} onChange={event => setProfile(event.target.value)}>
        <option value="">Default</option>
        {profiles.map(item => <option key={item.id} value={item.id}>{item.name} · {item.model}</option>)}
      </select></label>}
    </div>
    <PendingProposals projectId={projectId} />
    <div ref={logRef} className="chat-dock-log" role="log" aria-label="Conversation" aria-live="polite">
      {state.entries.length === 0 && <p className="empty-copy">Ask the {roleLabel(role).toLowerCase()} anything about this project. It sees the page you are on{focus.selection ? ` (${focus.selection})` : ''}.</p>}
      <MessageList state={state} projectId={projectId} onDecide={session.decide} />
      {busy && <p className="room-typing">The room is working…</p>}
      {state.status === 'stopped' && <p className="room-typing">Stopped.</p>}
      {state.status === 'error' && <div className="error-text" role="alert">{state.error}
        <button type="button" className="mini-button" onClick={session.retry}>Retry</button></div>}
    </div>
    <form className="room-chat-compose" onSubmit={send}>
      <textarea aria-label="Message the room" value={draft} rows={2} placeholder="What does Will want from Edward?"
        onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) send(event) }} />
      {busy
        ? <button className="button quiet" type="button" onClick={session.stop}>Stop</button>
        : <button className="button primary" type="submit" disabled={!draft.trim()}>Send</button>}
    </form>
    {!busy && lastIsAnswer && state.interrupts.length === 0 && <button type="button" className="mini-button chat-regenerate" onClick={session.regenerate}>Regenerate</button>}
  </aside>
}
