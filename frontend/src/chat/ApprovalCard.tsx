import { useState } from 'react'
import type { Interrupt } from '@ag-ui/core'
import { toolLabel } from './labels'
import type { Decision, ToolEntry } from './reducer'
import { argsOf } from './registry'

type Props = { call: ToolEntry; interrupt?: Interrupt; onDecide: (decision: Decision) => void }

/** An in-chat approval: the exact write the agent wants to make, and the writer's Approve / Deny. */
export default function ApprovalCard({ call, interrupt, onDecide }: Props) {
  const [reason, setReason] = useState('')
  const decided = call.status === 'approved' || call.status === 'denied'
  return <section className={`chat-card approval ${call.status}`} aria-label={`Approve ${call.name}`}>
    <p className="chat-card-title">{decided ? (call.status === 'approved' ? 'Approved' : 'Denied') : 'Needs your approval'} · {toolLabel(call.name)}</p>
    <code className="chat-tool-name">{call.name}</code>
    <pre>{JSON.stringify(argsOf(call), null, 2)}</pre>
    {decided && call.reason && <p className="chat-card-lead">Reason: {call.reason}</p>}
    {decided && call.status === 'approved' && <p className="room-typing">Running the approved change…</p>}
    {!decided && interrupt && <div className="chat-approval-actions">
      <input aria-label={`Reason for ${call.name}`} placeholder="Reason (optional)" value={reason} onChange={event => setReason(event.target.value)} />
      <button type="button" className="button primary" onClick={() => onDecide({ approved: true, reason: reason.trim() || undefined })}>Approve</button>
      <button type="button" className="button quiet" onClick={() => onDecide({ approved: false, reason: reason.trim() || undefined })}>Deny</button>
    </div>}
    {!decided && !interrupt && <p className="empty-copy">This request expired with its turn.</p>}
  </section>
}
