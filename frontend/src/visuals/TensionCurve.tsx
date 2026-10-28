import { useState } from 'react'
import { Link } from 'react-router'
import type { StoryVisuals } from '../storyApi'
import { useProjectId } from '../project/useProjectId'
import { actStarts, formatIntensity, intensityY, linePath, sceneX, tensionRuns } from './charts'
import { ToolHead, WithVisuals } from './VisualsLayout'

const W = 900
const H = 300
const PAD = 28

const label = (type: string) => type.replace(/_/g, ' ')

/** The tension curve: the cast's average intensity scene by scene, with act breaks and typed beats marked. */
export function TensionChart({ visuals }: { visuals: StoryVisuals }) {
  const [focus, setFocus] = useState<number | null>(null)
  const { scenes, milestones } = visuals
  const runs = tensionRuns(scenes, W, H, PAD)
  const rated = scenes.filter(scene => scene.intensity !== null).length
  const placed = milestones.filter(item => item.scene_index !== null)
  const focused = scenes.find(scene => scene.id === focus)
  return <figure className="visual-figure">
    <svg viewBox={`0 0 ${W} ${H}`} className="tension-chart" role="img"
      aria-label={`Tension curve across ${scenes.length} scenes, ${rated} with intensity, ${placed.length} milestones`}>
      <line className="chart-zero" x1={PAD} x2={W - PAD} y1={intensityY(0, H, PAD)} y2={intensityY(0, H, PAD)} />
      <text className="chart-axis" x={4} y={intensityY(5, H, PAD) + 4}>+5</text>
      <text className="chart-axis" x={4} y={intensityY(0, H, PAD) + 4}>0</text>
      <text className="chart-axis" x={4} y={intensityY(-5, H, PAD) + 4}>−5</text>
      {actStarts(visuals).map(act => {
        const x = sceneX(act.index, scenes.length, W, PAD)
        return <g key={act.id} className="chart-act"><line x1={x} x2={x} y1={PAD / 2} y2={H - PAD / 2} /><text x={x + 4} y={PAD / 2 + 8}>{act.title}</text></g>
      })}
      {placed.map(item => {
        const x = sceneX(item.scene_index ?? 0, scenes.length, W, PAD)
        return <g key={item.beat_id} className={`chart-milestone ${item.beat_type}`}>
          <line x1={x} x2={x} y1={PAD} y2={H - PAD} />
          <text x={x + 3} y={H - 6}>{item.title}</text>
          <title>{`${item.title} (${label(item.beat_type)})`}</title>
        </g>
      })}
      {runs.map(run => <path key={run[0].scene.id} className="chart-line" d={linePath(run)} />)}
      {runs.flat().map(point => <circle key={point.scene.id} className={point.scene.id === focus ? 'chart-point focused' : 'chart-point'} cx={point.x} cy={point.y} r={point.scene.id === focus ? 6 : 4}>
        <title>{`${point.scene.index + 1}. ${point.scene.heading}: ${formatIntensity(point.scene.intensity)}`}</title>
      </circle>)}
    </svg>
    <figcaption>{focused ? `${focused.index + 1}. ${focused.heading} · ${formatIntensity(focused.intensity)} from ${focused.event_count} event${focused.event_count === 1 ? '' : 's'}` : 'Hover a row below to find its scene on the curve.'}</figcaption>
    <table className="visual-table">
      <caption className="visually-hidden">Intensity by scene</caption>
      <thead><tr><th scope="col">#</th><th scope="col">Scene</th><th scope="col">Intensity</th><th scope="col">Events</th><th scope="col">Milestones</th></tr></thead>
      <tbody>{scenes.map(scene => <tr key={scene.id} onMouseEnter={() => setFocus(scene.id)} onFocus={() => setFocus(scene.id)} tabIndex={0}>
        <td>{scene.index + 1}</td><td>{scene.heading}</td><td>{formatIntensity(scene.intensity)}</td><td>{scene.event_count}</td>
        <td>{milestones.filter(item => item.scene_id === scene.id).map(item => item.title).join(', ')}</td>
      </tr>)}</tbody>
    </table>
  </figure>
}

/** The tension curve page. */
export default function TensionCurvePage() {
  const projectId = useProjectId()
  return <>
    <ToolHead title="Tension curve">The cast’s average intensity (−5 a low, +5 a high) through the script, scene by scene in narrative order. Set intensity on characters’ timeline events; typed beats (inciting incident, midpoint, climax…) are marked where their first scene falls.</ToolHead>
    <WithVisuals>{visuals => {
      if (!visuals.scenes.length) return <p className="empty-copy">No scenes yet. Write some in the <Link to={`/projects/${projectId}/script`}>script</Link> first.</p>
      const unplaced = visuals.milestones.filter(item => item.scene_index === null)
      return <>
        {visuals.scenes.every(scene => scene.intensity === null) && <p className="empty-copy">No scene has rated events yet. Link characters’ timeline events to scenes (or shared moments) and give them an intensity.</p>}
        <TensionChart visuals={visuals} />
        {unplaced.length > 0 && <p className="empty-copy">Not linked to a scene yet: {unplaced.map(item => `${item.title} (${label(item.beat_type)})`).join(', ')}.</p>}
      </>
    }}</WithVisuals>
  </>
}
