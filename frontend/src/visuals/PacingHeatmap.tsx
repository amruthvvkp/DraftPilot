import { Link } from 'react-router'
import type { StoryVisuals } from '../storyApi'
import { useProjectId } from '../project/useProjectId'
import { clock, formatIntensity, intensityColor, pacingByAct } from './charts'
import { ToolHead, WithVisuals } from './VisualsLayout'

/** One row per act; each cell is a scene, as wide as its runtime and coloured by its intensity. */
export function PacingGrid({ visuals }: { visuals: StoryVisuals }) {
  const acts = pacingByAct(visuals).filter(act => act.scenes.length)
  return <>
    <div className="pacing-grid" role="list" aria-label="Pacing by act">
      {acts.map(act => <section key={act.id} className="pacing-row" role="listitem" aria-label={act.title}>
        <header><strong>{act.title}</strong><small>{clock(act.runtime)} · {Math.round(act.share * 100)}% · avg {formatIntensity(act.intensity)}</small></header>
        <div className="pacing-cells">
          {act.scenes.map(scene => <span key={scene.id} className="pacing-cell" style={{ flexGrow: scene.share, background: intensityColor(scene.intensity) }}
            title={`${scene.index + 1}. ${scene.heading} · ${clock(scene.runtime_seconds)} · ${formatIntensity(scene.intensity)}`}
            aria-label={`${scene.heading}: ${clock(scene.runtime_seconds)}, intensity ${formatIntensity(scene.intensity)}`} role="img" />)}
        </div>
      </section>)}
    </div>
    <p className="pacing-legend" aria-hidden="true">
      <span style={{ background: intensityColor(-5) }} />−5 low <span style={{ background: intensityColor(0) }} />0 <span style={{ background: intensityColor(5) }} />+5 high <span style={{ background: intensityColor(null) }} />no events
    </p>
    <table className="visual-table">
      <caption className="visually-hidden">Runtime and intensity by act</caption>
      <thead><tr><th scope="col">Act</th><th scope="col">Scenes</th><th scope="col">Runtime</th><th scope="col">Share</th><th scope="col">Avg intensity</th><th scope="col">Peak</th></tr></thead>
      <tbody>{acts.map(act => <tr key={act.id}>
        <th scope="row">{act.title}</th><td>{act.scenes.length}</td><td>{clock(act.runtime)}</td><td>{Math.round(act.share * 100)}%</td>
        <td>{formatIntensity(act.intensity)}</td><td>{formatIntensity(act.peak)}</td>
      </tr>)}</tbody>
    </table>
  </>
}

/** The pacing heatmap page. */
export default function PacingHeatmapPage() {
  const projectId = useProjectId()
  return <>
    <ToolHead title="Pacing heatmap">Scene runtime against intensity, act by act. Each cell is a scene, sized by its estimated runtime (the same estimate as the timeline board) and coloured by the cast’s average intensity. The act average is weighted by runtime.</ToolHead>
    <WithVisuals>{visuals => visuals.scenes.length
      ? <PacingGrid visuals={visuals} />
      : <p className="empty-copy">No scenes yet. Write some in the <Link to={`/projects/${projectId}/script`}>script</Link> first.</p>}</WithVisuals>
  </>
}
