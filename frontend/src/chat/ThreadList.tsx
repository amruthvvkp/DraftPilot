import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { keys } from '../data/queries'
import ConfirmDialog from '../project/ConfirmDialog'
import { chatApi, type ChatThread } from './api'

type Props = { projectId: number; currentId: string; onOpen: (id: string) => void; onNew: () => void }

function ThreadRow({ thread, current, onOpen, onRename, onDelete }: { thread: ChatThread; current: boolean; onOpen: () => void; onRename: (title: string) => void; onDelete: () => void }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(thread.title)
  if (editing) {
    return <li className="chat-thread editing"><form onSubmit={event => { event.preventDefault(); if (title.trim()) onRename(title.trim()); setEditing(false) }}>
      <input aria-label={`Rename ${thread.title}`} value={title} autoFocus onChange={event => setTitle(event.target.value)} onKeyDown={event => { if (event.key === 'Escape') setEditing(false) }} />
      <button type="submit" className="mini-button">Save</button>
    </form></li>
  }
  return <li className={current ? 'chat-thread current' : 'chat-thread'}>
    <button type="button" className="chat-thread-open" aria-label={`Open ${thread.title}`} aria-current={current ? 'true' : undefined} onClick={onOpen}>{thread.title}<small>{new Date(thread.updated_at).toLocaleString()}</small></button>
    <button type="button" className="mini-button" aria-label={`Rename ${thread.title}`} onClick={() => { setTitle(thread.title); setEditing(true) }}>✎</button>
    <button type="button" className="mini-button danger" aria-label={`Delete ${thread.title}`} onClick={onDelete}>✕</button>
  </li>
}

/** The project's conversations: start, switch, rename, delete. */
export default function ThreadList({ projectId, currentId, onOpen, onNew }: Props) {
  const queryClient = useQueryClient()
  const { data: threads } = useQuery({ queryKey: keys.threads(projectId), queryFn: () => chatApi.threads(projectId) })
  const [deleting, setDeleting] = useState<ChatThread | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.threads(projectId) })

  async function rename(thread: ChatThread, title: string): Promise<void> {
    await chatApi.renameThread(projectId, thread.id, title).catch(() => undefined)
    await refresh()
  }
  async function remove(thread: ChatThread): Promise<void> {
    setDeleting(null)
    await chatApi.deleteThread(projectId, thread.id).catch(() => undefined)
    if (thread.id === currentId) onNew()
    await refresh()
  }

  return <section className="chat-threads" aria-label="Conversations">
    <button type="button" className="button quiet" onClick={onNew}>＋ New conversation</button>
    {threads && threads.length === 0 && <p className="empty-copy">No saved conversations yet.</p>}
    <ul>{(threads ?? []).map(thread => <ThreadRow key={thread.id} thread={thread} current={thread.id === currentId}
      onOpen={() => onOpen(thread.id)} onRename={title => void rename(thread, title)} onDelete={() => setDeleting(thread)} />)}</ul>
    {deleting && <ConfirmDialog title={`Delete “${deleting.title}”?`} confirmLabel="Delete conversation" onCancel={() => setDeleting(null)} onConfirm={() => void remove(deleting)}>
      <p>The conversation and its history are removed. Anything it changed in the project stays.</p>
    </ConfirmDialog>}
  </section>
}
