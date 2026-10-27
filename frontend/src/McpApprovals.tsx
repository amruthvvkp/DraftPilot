import { useEffect, useState } from 'react'
import { CLIENT_ID, decideMcpApproval, listMcpApprovals, McpApproval, subscribeProjectEvents } from './api'

/** List pending MCP approval requests so the writer, not the client, decides external writes. */
export default function McpApprovals({ projectId }: { projectId: number }) {
  const [approvals, setApprovals] = useState<McpApproval[]>([])
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try { setApprovals(await listMcpApprovals(projectId, 'pending')) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load approvals') }
  }

  useEffect(() => {
    void refresh()
    // Live via SSE; a slow poll covers a dropped stream.
    const unsubscribe = subscribeProjectEvents(projectId, event => { if (event.kind === 'approval.changed' && event.client !== CLIENT_ID) void refresh() })
    const timer = window.setInterval(() => void refresh(), 30000)
    return () => { window.clearInterval(timer); unsubscribe() }
  }, [projectId])

  async function decide(approvalId: number, decision: 'approve' | 'reject'): Promise<void> {
    setError('')
    try { await decideMcpApproval(projectId, approvalId, decision); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to record decision') }
  }

  if (approvals.length === 0 && !error) return null
  return <section className="mcp-approvals" aria-label="External agent approvals">
    <p className="eyebrow">EXTERNAL AGENT REQUESTS / {approvals.length}</p>
    {error && <p role="alert" className="copilot-error">{error}</p>}
    {approvals.map(approval => <article className="copilot-proposal" key={approval.id}>
      <div className="proposal-meta"><strong>{approval.client_id}</strong><span className="proposal-status proposed">{approval.capability} · {approval.action}</span></div>
      <pre>{JSON.stringify(approval.summary, null, 2)}</pre>
      <p className="approval-expiry">Expires {new Date(approval.expires_at).toLocaleTimeString()}</p>
      <div className="proposal-actions">
        <button className="button primary" onClick={() => void decide(approval.id, 'approve')}>Approve request</button>
        <button className="button quiet" onClick={() => void decide(approval.id, 'reject')}>Reject</button>
      </div>
    </article>)}
  </section>
}
