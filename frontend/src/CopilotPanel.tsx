import { useEffect, useState, type FormEvent } from 'react'
import { AgentProposal, AgentRole, approveAgentProposal, CopilotMessage, getAgentProposals, getAgentRoles, getCopilotMessages, getWorkflowRun, listProviderProfiles, ProviderProfile, rollbackAgentProposal, startCopilotRun } from './api'

type CopilotPanelProps = { projectId: number; page?: string; artifact?: string | null; selection?: string | null; refreshToken?: number }

export default function CopilotPanel({ projectId, page = window.location.pathname, artifact = null, selection = null, refreshToken = 0 }: CopilotPanelProps) {
  const [proposals, setProposals] = useState<AgentProposal[]>([])
  const [messages, setMessages] = useState<CopilotMessage[]>([])
  const [roles, setRoles] = useState<AgentRole[]>([])
  const [profiles, setProfiles] = useState<ProviderProfile[]>([])
  const [selectedProfile, setSelectedProfile] = useState('')
  const [selectedRole, setSelectedRole] = useState('story_architect')
  const [permissionMode, setPermissionMode] = useState<'chat_only' | 'suggest' | 'scoped_edit' | 'project_edit'>('chat_only')
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const activeTools = page.endsWith('/timeline')
    ? ['timeline.propose', 'screenplay.read', 'context.read', 'revisions.read']
    : page.endsWith('/studio')
      ? ['outline.read', 'context.read', 'knowledge_graph.read', 'revisions.read']
      : ['screenplay.read', 'context.read', 'revisions.read']

  async function refresh(): Promise<void> {
    try {
      const [nextProposals, nextMessages, nextRoles, nextProfiles] = await Promise.all([getAgentProposals(projectId), getCopilotMessages(projectId), getAgentRoles(), listProviderProfiles()])
      setProposals(nextProposals)
      setMessages(nextMessages)
      setRoles(nextRoles)
      setProfiles(nextProfiles)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load Copilot context') }
  }

  useEffect(() => { void refresh() }, [projectId, refreshToken])

  async function approve(proposalId: number): Promise<void> {
    try { await approveAgentProposal(projectId, proposalId); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to approve proposal') }
  }

  async function rollback(proposalId: number): Promise<void> {
    try { await rollbackAgentProposal(projectId, proposalId); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to rollback proposal') }
  }

  async function send(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!draft.trim()) return
    try {
      const pending = await startCopilotRun(projectId, {
        content: draft.trim(), page, artifact, selection,
        instruction_layers: { agent_role: selectedRole, permission_mode: permissionMode, provider_profile_id: selectedProfile ? Number(selectedProfile) : null }, citations: [], active_tools: activeTools,
      })
      setMessages(current => [...current, pending.message])
      setDraft('')
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 250))
        const run = await getWorkflowRun(projectId, pending.run.id)
        if (run.status === 'succeeded') { await refresh(); return }
        if (run.status === 'failed' || run.status === 'cancelled') { setError(run.error ?? `Copilot run ${run.status}`); return }
      }
      setError('Copilot is still running; the conversation will resume when you return.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save Copilot message') }
  }

  return <section className="copilot-panel" aria-label="Copilot and agent proposals">
    <div className="panel-label"><span>Copilot</span><span className="context-badge">Server scoped</span></div>
    <div className="copilot-intro"><span className="copilot-mark">✦</span><div><strong>Make the next decision visible.</strong><p>Agent changes arrive as typed proposals. You stay in control.</p></div></div>
    <div className="copilot-controls"><label>Agent<select value={selectedRole} onChange={event => setSelectedRole(event.target.value)}>{roles.map(role => <option key={role.key} value={role.key}>{role.label}</option>)}</select></label><label>Permission<select value={permissionMode} onChange={event => setPermissionMode(event.target.value as typeof permissionMode)}><option value="chat_only">Chat only</option><option value="suggest">Suggest</option><option value="scoped_edit">Scoped edit</option><option value="project_edit">Project edit</option></select></label>{profiles.length > 0 && <label>Provider<select value={selectedProfile} onChange={event => setSelectedProfile(event.target.value)}><option value="">Process default</option>{profiles.filter(profile => profile.enabled).map(profile => <option key={profile.id} value={profile.id}>{profile.name} · {profile.model}</option>)}</select></label>}</div>
    <div className="agent-tools"><p className="eyebrow warm">ACTIVE TOOLS</p>{activeTools.map(tool => <span key={tool}>{tool}</span>)}</div>
    <div className="copilot-messages">{messages.map(message => <article className={`copilot-message ${message.role}`} key={message.id}><div className="copilot-message-meta"><strong>{message.role}</strong><span>{message.page}{message.artifact ? ` · ${message.artifact}` : ''}{message.selection ? ` · ${message.selection}` : ''}</span></div><p>{message.content}</p>{message.citations.length > 0 && <div className="copilot-citations"><small>Retrieved sources</small>{message.citations.map((citation, index) => <span key={`${String(citation.source_id ?? index)}-${String(citation.content_version ?? '')}`}>{String(citation.source_id ?? 'project context')} · v{String(citation.content_version ?? '?')}</span>)}</div>}</article>)}</div>
    <form className="copilot-compose" onSubmit={event => void send(event)}><input value={draft} onChange={event => setDraft(event.target.value)} placeholder="Ask the studio…" aria-label="Copilot message" /><button className="button primary" type="submit">Send</button></form>
    {error && <p className="copilot-error">{error}</p>}
    <div className="proposal-list"><p className="eyebrow">PROPOSALS / {proposals.length}</p>{proposals.length === 0 && <p className="copilot-empty">No pending proposals. Ask an enabled agent to suggest a typed change.</p>}{proposals.map(proposal => <article className="copilot-proposal" key={proposal.id}><div className="proposal-meta"><strong>#{proposal.id} {proposal.target_kind}</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div><pre>{JSON.stringify(proposal.diff || proposal.operation, null, 2)}</pre>{proposal.status === 'proposed' && <button className="button primary" onClick={() => void approve(proposal.id)}>Approve change</button>}{proposal.status === 'approved' && <button className="button quiet" onClick={() => void rollback(proposal.id)}>Rollback</button>}</article>)}</div>
  </section>
}
