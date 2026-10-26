import type { Interrupt } from '@ag-ui/core'
import ApprovalCard from './ApprovalCard'
import Markdown from './Markdown'
import type { ChatState, Decision, Entry } from './reducer'
import { ToolCard } from './registry'

type Props = { state: ChatState; projectId: number; onDecide: (interruptId: string, decision: Decision) => void }

function EntryView({ entry, interrupts, projectId, onDecide }: { entry: Entry; interrupts: Interrupt[]; projectId: number; onDecide: Props['onDecide'] }) {
  if (entry.kind === 'user') return <article className="room-message user"><p className="message-text">{entry.text}</p></article>
  if (entry.kind === 'text') return <article className="room-message assistant"><Markdown text={entry.text} /></article>
  if (entry.kind === 'reasoning') return <details className="reasoning"><summary>Thinking</summary><p>{entry.text}</p></details>
  const interrupt = interrupts.find(item => item.toolCallId === entry.id)
  if (interrupt || entry.status === 'awaiting' || ((entry.status === 'approved' || entry.status === 'denied') && entry.result === undefined)) {
    return <ApprovalCard call={entry} interrupt={interrupt} onDecide={decision => interrupt && onDecide(interrupt.id, decision)} />
  }
  return <ToolCard call={entry} projectId={projectId} />
}

/** The conversation: writer and assistant messages, reasoning, and a card per tool call. */
export default function MessageList({ state, projectId, onDecide }: Props) {
  return <>{state.entries.map(entry => <EntryView key={`${entry.kind}-${entry.id}`} entry={entry} interrupts={state.interrupts} projectId={projectId} onDecide={onDecide} />)}</>
}
