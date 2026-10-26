import type { ProjectWorkspace, Scene, ScreenplayBlock } from '../api'
import SceneCreationPanel from '../SceneCreationPanel'

export type Timing = { duration: number; start: number; end: number }

export function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

function sceneStatus(scene: Scene, blockList: ScreenplayBlock[] | undefined): 'ready' | 'in progress' | 'needs content' {
  if (!scene.body.trim() && (!blockList || blockList.length === 0)) return 'needs content'
  const hasDialogue = blockList?.some(b => b.element_type === 'dialogue')
  const hasCharacter = blockList?.some(b => b.element_type === 'character')
  return hasDialogue && hasCharacter ? 'ready' : 'in progress'
}

export type SceneMoves = { up?: () => void; down?: () => void; toAct: (actId: number) => void; remove: () => void }

function SceneActions({ scene, workspace, moves }: { scene: Scene; workspace: ProjectWorkspace; moves: SceneMoves }) {
  return <div className="scene-actions" role="group" aria-label="Selected scene actions">
    <button type="button" className="mini-button" aria-label="Move scene up" disabled={!moves.up} onClick={moves.up}>↑</button>
    <button type="button" className="mini-button" aria-label="Move scene down" disabled={!moves.down} onClick={moves.down}>↓</button>
    {workspace.acts.length > 1 && <select aria-label="Move scene to act" value={scene.act_id} onChange={event => moves.toAct(Number(event.target.value))}>
      {workspace.acts.map(act => <option key={act.id} value={act.id}>{act.title || `Act ${act.position + 1}`}</option>)}
    </select>}
    <button type="button" className="mini-button danger" onClick={moves.remove}>Delete scene</button>
  </div>
}

type NavigatorProps = {
  projectId: number
  workspace: ProjectWorkspace
  selectedId: number | null
  onSelect: (sceneId: number) => void
  timings: Map<number, Timing>
  totalRuntime: number
  targetRuntime: number
  moves: SceneMoves | null
}

/** The scene list by act, with runtime, scene actions and the add-scene form. */
export default function SceneNavigator({ projectId, workspace, selectedId, onSelect, timings, totalRuntime, targetRuntime, moves }: NavigatorProps) {
  const progressPercent = Math.min(100, Math.round((totalRuntime / targetRuntime) * 100))
  const driftSeconds = totalRuntime - targetRuntime
  const pacingDrift = totalRuntime === 0 ? 'Not started' : Math.abs(driftSeconds) <= 300 ? 'On pace' : driftSeconds > 0 ? `+${Math.round(driftSeconds / 60)}m ahead` : `-${Math.round(Math.abs(driftSeconds) / 60)}m behind`
  const acts = [...workspace.acts].sort((a, b) => a.position - b.position)
  const selected = workspace.scenes.find(scene => scene.id === selectedId)
  return <aside className="navigator">
    <div className="panel-label"><span>Navigator</span><span>{workspace.scenes.length.toString().padStart(2, '0')} scenes</span></div>
    <div className="runtime-summary" aria-label="Screenplay runtime">
      <div className="runtime-numbers"><span>Estimated runtime</span><strong>{clock(totalRuntime)} / {clock(targetRuntime)}</strong></div>
      <div className="runtime-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100} aria-label="Runtime progress">
        <div className="runtime-fill" style={{ width: `${progressPercent}%` }} />
      </div>
      <div className="runtime-meta">
        <small className="runtime-drift">Pacing: {pacingDrift}</small>
        <small className="runtime-note">Scene time accumulates as the draft grows.</small>
      </div>
    </div>
    {workspace.scenes.length === 0 && <p className="empty-copy">Your scene list will appear here as the story takes shape.</p>}
    {acts.map(act => <div className="act-group" key={act.id}>
      <p className="act-title">{act.title || `Act ${act.position + 1}`}</p>
      {workspace.scenes.filter(scene => scene.act_id === act.id).sort((a, b) => a.position - b.position).map(scene => {
        const timing = timings.get(scene.id) ?? { duration: 30, start: 0, end: 30 }
        return <div key={scene.id}><button className={scene.id === selectedId ? 'scene-link selected' : 'scene-link'} onClick={() => onSelect(scene.id)} aria-current={scene.id === selectedId ? 'true' : undefined}>
          <div className="scene-link-header">
            <span>{String(scene.position + 1).padStart(2, '0')}</span>
            <strong>{scene.heading}</strong>
            <span className="scene-duration">{clock(timing.duration)}</span>
          </div>
          <div className="scene-link-meta"><small>{clock(timing.start)}–{clock(timing.end)} · {sceneStatus(scene, workspace.blocks[scene.id])}</small></div>
        </button>{scene.id === selectedId && moves && <SceneActions scene={scene} workspace={workspace} moves={moves} />}</div>
      })}
    </div>)}
    {workspace.scenes.length > 0 && <SceneCreationPanel projectId={projectId} screenplayId={workspace.screenplay?.id} afterScene={selected} onCreated={onSelect} />}
  </aside>
}
