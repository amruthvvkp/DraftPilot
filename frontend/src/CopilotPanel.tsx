import { useEffect, useState, type FormEvent } from 'react'
import { AgentProposal, AgentRole, approveAgentProposal, CopilotMessage, getAgentProposals, getAgentRoles, getCopilotMessages, rollbackAgentProposal, sendCopilotMessage } from './api'

type CopilotPanelProps = { projectId: number }

export default function CopilotPanel({ projectId }: CopilotPanelProps) {
  const [proposals, setProposals] = useState<AgentProposal[]>([])
  const [messages, setMessages] = useState<CopilotMessage[]>([])
  const [roles, setRoles] = useState<AgentRole[]>([])
  const [selectedRole, setSelectedRole] = useState('story_architect')
  const [permissionMode, setPermissionMode] = useState<'chat_only' | 'suggest' | 'scoped_edit' | 'project_edit'>('chat_only')
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try {
      const [nextProposals, nextMessages, nextRoles] = await Promise.all([getAgentProposals(projectId), getCopilotMessages(projectId), getAgentRoles()])
      setProposals(nextProposals)
      setMessages(nextMessages)
      setRoles(nextRoles)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load Copilot context') }
  }

  useEffect(() => { void refresh() }, [projectId])

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
      const message = await sendCopilotMessage(projectId, {
        content: draft.trim(), page: window.location.pathname, artifact: null, selection: null,
        instruction_layers: { agent_role: selectedRole, permission_mode: permissionMode }, citations: [], active_tools: ['screenplay.read', 'context.read', 'revisions.read'],
      })
      setMessages(current => [...current, message])
      setDraft('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save Copilot message') }
  }

  return <section className="copilot-panel" aria-label="Copilot and agent proposals">
    <div className="panel-label"><span>Copilot</span><span className="context-badge">Server scoped</span></div>
    <div className="copilot-intro"><span className="copilot-mark">✦</span><div><strong>Make the next decision visible.</strong><p>Agent changes arrive as typed proposals. You stay in control.</p></div></div>
    <div className="copilot-controls"><label>Agent<select value={selectedRole} onChange={event => setSelectedRole(event.target.value)}>{roles.map(role => <option key={role.key} value={role.key}>{role.label}</option>)}</select></label><label>Permission<select value={permissionMode} onChange={event => setPermissionMode(event.target.value as typeof permissionMode)}><option value="chat_only">Chat only</option><option value="suggest">Suggest</option><option value="scoped_edit">Scoped edit</option><option value="project_edit">Project edit</option></select></label></div>
    <div className="agent-tools"><p className="eyebrow warm">ACTIVE TOOLS</p><span>screenplay.read</span><span>context.read</span><span>revisions.read</span></div>
    <div className="copilot-messages">{messages.map(message => <p className={`copilot-message ${message.role}`} key={message.id}><strong>{message.role}</strong>{message.content}</p>)}</div>
    <form className="copilot-compose" onSubmit={event => void send(event)}><input value={draft} onChange={event => setDraft(event.target.value)} placeholder="Ask the studio…" aria-label="Copilot message" /><button className="button primary" type="submit">Send</button></form>
    {error && <p className="copilot-error">{error}</p>}
    <div className="proposal-list"><p className="eyebrow">PROPOSALS / {proposals.length}</p>{proposals.length === 0 && <p className="copilot-empty">No pending proposals. Ask an enabled agent to suggest a typed change.</p>}{proposals.map(proposal => <article className="copilot-proposal" key={proposal.id}><div className="proposal-meta"><strong>#{proposal.id} {proposal.target_kind}</strong><span className={`proposal-status ${proposal.status}`}>{proposal.status}</span></div><pre>{JSON.stringify(proposal.diff || proposal.operation, null, 2)}</pre>{proposal.status === 'proposed' && <button className="button primary" onClick={() => void approve(proposal.id)}>Approve change</button>}{proposal.status === 'approved' && <button className="button quiet" onClick={() => void rollback(proposal.id)}>Rollback</button>}</article>)}</div>
  </section>
}
