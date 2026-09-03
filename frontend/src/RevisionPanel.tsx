import { useEffect, useState } from 'react'
import { createSceneRevision, diffSceneRevisions, listSceneRevisions, restoreSceneRevision, SceneRevision } from './api'
import EvaluationPanel from './EvaluationPanel'
import DualDialoguePanel from './DualDialoguePanel'
import SceneCreationPanel from './SceneCreationPanel'
import BlockCreationPanel from './BlockCreationPanel'
import EditorViewMode from './EditorViewMode'

type RevisionPanelProps = { projectId: number; sceneId: number; sceneVersion: number; screenplayId: number }

export default function RevisionPanel({ projectId, sceneId, sceneVersion, screenplayId }: RevisionPanelProps) {
  const [revisions, setRevisions] = useState<SceneRevision[]>([])
  const [message, setMessage] = useState('')
  const [diff, setDiff] = useState('')
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try { setRevisions(await listSceneRevisions(projectId, sceneId)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load revisions') }
  }
  useEffect(() => { void refresh() }, [projectId, sceneId])

  async function snapshot(): Promise<void> {
    try { await createSceneRevision(projectId, sceneId, message.trim() || 'Named snapshot'); setMessage(''); await refresh() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save snapshot') }
  }
  async function review(): Promise<void> {
    if (revisions.length < 2) return
    try { setDiff((await diffSceneRevisions(projectId, sceneId, revisions[revisions.length - 2].id, revisions[revisions.length - 1].id)).diff) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to compare revisions') }
  }
  async function restore(revisionId: number): Promise<void> {
    try { await restoreSceneRevision(projectId, sceneId, revisionId, sceneVersion, ['heading', 'blocks']); await refresh() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to restore revision') }
  }

  return <><section className="revision-panel" aria-label="Scene revisions"><div className="panel-label"><span>Snapshots</span><span>{revisions.length}</span></div><div className="revision-create"><input value={message} onChange={event => setMessage(event.target.value)} placeholder="Name this snapshot" aria-label="Snapshot name" /><button className="mini-button" onClick={() => void snapshot()}>Save</button></div>{revisions.map(revision => <div className="revision-row" key={revision.id}><span>#{revision.rev_number}</span><strong>{revision.message || 'Unnamed snapshot'}</strong><button className="mini-button" onClick={() => void restore(revision.id)}>Restore</button></div>)}{revisions.length > 1 && <button className="button quiet" onClick={() => void review()}>Review latest diff</button>}{diff && <pre className="revision-diff">{diff}</pre>}{error && <p className="copilot-error">{error}</p>}</section><EditorViewMode /><SceneCreationPanel projectId={projectId} sceneId={sceneId} /><BlockCreationPanel projectId={projectId} sceneId={sceneId} /><DualDialoguePanel projectId={projectId} sceneId={sceneId} /><EvaluationPanel projectId={projectId} screenplayId={screenplayId} /></>
}
