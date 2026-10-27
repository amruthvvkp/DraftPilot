import { useState } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { refreshStoryTwin } from '../api'
import { errorMessage, keys, useBeats, useCharacters, useStoryline, useTwin, useWorkspace } from '../data/queries'
import { projectStages, type Stage } from './progress'
import { useProjectId } from './useProjectId'

function StageGaps({ stage }: { stage: Stage }) {
  return <section className={`context-stage ${stage.state}`} aria-label={`${stage.label} gaps`}>
    <div className="story-detail-head"><h3><Link to={stage.to}>{stage.label}</Link></h3><small>{stage.summary}</small></div>
    {stage.gaps.length === 0
      ? <p className="settings-success">Nothing missing.</p>
      : <ul>{stage.gaps.map(gap => <li key={gap.label}><Link to={gap.to}>{gap.label}</Link></li>)}</ul>}
  </section>
}

/** What the agents will see: the exact Story-twin brief, plus every empty field per stage with a link to fill it. */
export default function ContextMapPage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const twin = useTwin(projectId)
  const stages = projectStages({
    projectId,
    storyline: useStoryline(projectId).data,
    characters: useCharacters(projectId).data,
    beats: useBeats(projectId).data,
    workspace: useWorkspace(projectId).data,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    setBusy(true); setError('')
    try { await refreshStoryTwin(projectId); await queryClient.invalidateQueries({ queryKey: keys.project(projectId) }) }
    catch (reason) { setError(errorMessage(reason, 'Unable to refresh the twin')) } finally { setBusy(false) }
  }

  return <main className="story-page">
    <header className="story-head">
      <p className="eyebrow warm">CONTEXT MAP</p>
      <h1>What the agents see</h1>
      <p>Every agent in the room, and any MCP client, starts from this brief. Fill the gaps below and it grows with you.</p>
    </header>
    <div className="context-map">
      <section className="story-card" aria-label="Agent brief">
        <div className="story-detail-head"><h2>Agent brief</h2>
          <button className="button quiet" type="button" onClick={() => void refresh()} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh from the draft'}</button>
        </div>
        {(error || twin.error) && <p className="notice" role="alert">{error || errorMessage(twin.error, 'Unable to load the brief')}</p>}
        {twin.data ? <pre className="context-brief">{twin.data.brief.trim() || 'The brief is empty. Start with the storyline.'}</pre> : !twin.error && <p className="empty-copy">Loading…</p>}
      </section>
      <div className="context-stages">{stages.map(stage => <StageGaps key={stage.key} stage={stage} />)}</div>
    </div>
  </main>
}
