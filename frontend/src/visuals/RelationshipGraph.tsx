import { useState } from 'react'
import { Link } from 'react-router'
import type { StoryVisuals, VisualEdge } from '../storyApi'
import { useProjectId } from '../project/useProjectId'
import { circleLayout, edgeStrength, edgeWidth } from './charts'
import { ToolHead, WithVisuals } from './VisualsLayout'

const SIZE = 520

/** Describe how two characters are linked, in words. */
function describe(edge: VisualEdge): string {
  const parts = [
    edge.shared_moments ? `${edge.shared_moments} shared moment${edge.shared_moments === 1 ? '' : 's'}` : '',
    edge.shared_scenes ? `${edge.shared_scenes} shared scene${edge.shared_scenes === 1 ? '' : 's'}` : '',
    edge.relations.join(', '),
  ]
  return parts.filter(Boolean).join(' · ')
}

/** The cast as a ring; edges thicken with shared moments. Selecting a character highlights their links. */
export function CastGraph({ visuals }: { visuals: StoryVisuals }) {
  const [selected, setSelected] = useState<number | null>(null)
  const { characters, edges } = visuals
  const positions = circleLayout(characters.length, SIZE / 2, SIZE / 2, SIZE / 2 - 70)
  const at = new Map(characters.map((character, index) => [character.id, positions[index]]))
  const name = new Map(characters.map(character => [character.id, character.name]))
  const strongest = Math.max(0, ...edges.map(edgeStrength))
  const touches = (edge: VisualEdge) => selected !== null && (edge.source === selected || edge.target === selected)
  const ranked = [...edges].sort((a, b) => edgeStrength(b) - edgeStrength(a))
  const shown = selected === null ? ranked : ranked.filter(touches)
  return <div className="graph-layout">
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="cast-graph" role="img" aria-label={`Relationship graph of ${characters.length} characters and ${edges.length} links`}>
      {edges.map(edge => {
        const a = at.get(edge.source), b = at.get(edge.target)
        if (!a || !b) return null
        const state = selected === null ? '' : touches(edge) ? ' on' : ' off'
        return <line key={`${edge.source}-${edge.target}`} className={`graph-edge${edge.shared_moments ? '' : ' weak'}${state}`}
          x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={edgeWidth(edge, strongest)}>
          <title>{`${name.get(edge.source)} – ${name.get(edge.target)}: ${describe(edge)}`}</title>
        </line>
      })}
      {characters.map(character => {
        const point = at.get(character.id)!
        return <g key={character.id} className={`graph-node${selected === character.id ? ' on' : ''}`} transform={`translate(${point.x},${point.y})`}>
          <circle r={10 + Math.min(14, character.moment_count * 2)} />
          <text y={-(16 + Math.min(14, character.moment_count * 2))}>{character.name}</text>
        </g>
      })}
    </svg>
    <div className="graph-side">
      <div className="graph-cast" role="group" aria-label="Focus a character">
        {characters.map(character => <button key={character.id} type="button" aria-pressed={selected === character.id}
          onClick={() => setSelected(current => current === character.id ? null : character.id)}>{character.name}</button>)}
      </div>
      <h2 className="eyebrow">{selected === null ? 'Strongest links' : `Links of ${name.get(selected)}`}</h2>
      {shown.length ? <ol className="graph-links" aria-label="Links">
        {shown.map(edge => <li key={`${edge.source}-${edge.target}`}><strong>{name.get(edge.source)} – {name.get(edge.target)}</strong><small>{describe(edge)}</small></li>)}
      </ol> : <p className="empty-copy">No links yet.</p>}
    </div>
  </div>
}

/** The relationship graph page. */
export default function RelationshipGraphPage() {
  const projectId = useProjectId()
  return <>
    <ToolHead title="Relationship graph">Your cast and how tightly they are bound. A link is as strong as the shared moments the two characters take part in (shared scenes count a little); dashed links are scenes or named relationships only.</ToolHead>
    <WithVisuals>{visuals => visuals.characters.length
      ? <CastGraph visuals={visuals} />
      : <p className="empty-copy">No characters yet. Add some on the <Link to={`/projects/${projectId}/characters`}>Characters</Link> page.</p>}</WithVisuals>
  </>
}
