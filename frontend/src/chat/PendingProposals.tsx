import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type AgentProposal, approveAgentProposal, getAgentProposals, rejectAgentProposal, rollbackAgentProposal } from '../api'
import { keys } from '../data/queries'

const describe = (proposal: AgentProposal) => String(proposal.diff?.summary ?? `${proposal.target_kind} #${proposal.target_id}`)

/** Agent proposals waiting for the writer, from any chat, run or MCP client. */
export default function PendingProposals({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const { data: proposals } = useQuery({ queryKey: keys.proposals(projectId), queryFn: () => getAgentProposals(projectId) })
  const [error, setError] = useState('')
  const pending = (proposals ?? []).filter(proposal => proposal.status === 'proposed')
  const recent = (proposals ?? []).filter(proposal => proposal.status === 'approved').slice(-3)
  if (!pending.length && !recent.length) return null

  async function act(action: (projectId: number, id: number) => Promise<unknown>, id: number): Promise<void> {
    setError('')
    try { await action(projectId, id) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to update the proposal') }
    void queryClient.invalidateQueries({ queryKey: keys.project(projectId) })
  }

  return <details className="chat-pending" open>
    <summary>For your review · {pending.length}</summary>
    <ul aria-label="Proposals for your review">
      {pending.map(proposal => <li key={proposal.id} className="copilot-proposal">
        <div className="proposal-meta"><strong>#{proposal.id} {proposal.target_kind}</strong><span className="proposal-status proposed">proposed</span></div>
        <p>{describe(proposal)}</p>
        <div className="proposal-actions">
          <button type="button" className="button primary" onClick={() => void act(approveAgentProposal, proposal.id)}>Approve change</button>
          <button type="button" className="button quiet" onClick={() => void act(rejectAgentProposal, proposal.id)}>Reject</button>
        </div>
      </li>)}
      {recent.map(proposal => <li key={proposal.id} className="copilot-proposal">
        <div className="proposal-meta"><strong>#{proposal.id} {proposal.target_kind}</strong><span className="proposal-status approved">approved</span></div>
        <p>{describe(proposal)}</p>
        <button type="button" className="button quiet" onClick={() => void act(rollbackAgentProposal, proposal.id)}>Roll back</button>
      </li>)}
    </ul>
    {error && <p className="copilot-error" role="alert">{error}</p>}
  </details>
}
