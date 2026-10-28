import { Background, Controls, type Edge, Handle, MiniMap, type Node, type NodeProps, Position, ReactFlow, useNodesState } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { createContext, type KeyboardEvent, useContext, useEffect, useMemo } from 'react'
import type { Relationship, TimelineEvent } from '../storyApi'
import {
  CARD_HEIGHT, CARD_WIDTH, CAST_HEIGHT, castCurve, COLUMN_WIDTH, curvePath, curveY, HEADER_WIDTH, intensityBand, type JourneyLayout, laneCurve,
  LANE_PADDING, type PlacedCard, type PlacedMoment, SLOT_HEIGHT,
} from './layout'

/** What a card stands for: one character's event, or a shared moment. */
export type Target = { kind: 'event'; id: number } | { kind: 'moment'; id: number }
export type Move = 'earlier' | 'later' | 'previous-act' | 'next-act'

/** The page's handlers and view state, shared with every node without threading it through node data. */
export type JourneyActions = {
  axis: JourneyLayout['axis']
  selected: Target | null
  mergeIds: ReadonlySet<number>
  hoveredScene: number | null
  open: (target: Target) => void
  toggleMerge: (eventId: number) => void
  move: (target: Target, move: Move) => void
  addCard: (characterId: number) => void
}

export const JourneyContext = createContext<JourneyActions | null>(null)

/** Read the journey handlers (only inside the page). */
function useJourney(): JourneyActions {
  const value = useContext(JourneyContext)
  if (!value) throw new Error('Journey nodes need a JourneyContext')
  return value
}

/** Alt+arrows move the focused card: left/right earlier or later, up/down to the previous or next act. */
export function moveKey(event: KeyboardEvent, move: (move: Move) => void, narrative: boolean): void {
  if (!event.altKey) return
  const moves: Record<string, Move | undefined> = { ArrowLeft: 'earlier', ArrowRight: 'later', ArrowUp: narrative ? 'previous-act' : undefined, ArrowDown: narrative ? 'next-act' : undefined }
  const chosen = moves[event.key]
  if (!chosen) return
  event.preventDefault()
  move(chosen)
}

type LaneData = { name: string; role: string; characterId: number; height: number }
type ColumnData = { label: string; moved?: number; actLabel?: string; sceneId?: number }
type CardData = { card: PlacedCard; sceneId?: number }
type MomentSide = { event: TimelineEvent; name: string; top: number }
type MomentData = { item: PlacedMoment; sides: MomentSide[]; sceneId?: number }
type CurveData = { paths: { d: string; name: string; dots: { x: number; y: number }[] }[]; cast: string; width: number; height: number; castTop: number }

/** A lane's header: the character, an Add card button, and the relationship edge handles. */
function LaneHeader({ data }: NodeProps<Node<LaneData>>) {
  const { addCard } = useJourney()
  return <div className="journey-lane-head" style={{ width: HEADER_WIDTH - 16, height: data.height - 8 }}>
    <Handle type="source" id="out" position={Position.Left} isConnectable={false} />
    <Handle type="target" id="in" position={Position.Left} isConnectable={false} />
    <strong>{data.name}</strong>
    {data.role && <small>{data.role}</small>}
    <button type="button" className="button quiet small nodrag" onClick={() => addCard(data.characterId)}>Add card<span className="visually-hidden"> for {data.name}</span></button>
  </div>
}

/** A column header: a scene (with its old number when a proposal moved it), a beat or a story-time point. */
function ColumnHeader({ data }: NodeProps<Node<ColumnData>>) {
  const { hoveredScene } = useJourney()
  const hot = data.sceneId !== undefined && data.sceneId === hoveredScene
  return <div className={`journey-column-head${data.moved ? ' ghost' : ''}${hot ? ' highlight' : ''}`} style={{ width: COLUMN_WIDTH - 12 }}>
    {data.actLabel && <span className="journey-act-label">{data.actLabel}</span>}
    <strong title={data.label}>{data.label}</strong>
    {data.moved && <small>was #{data.moved}</small>}
  </div>
}

/** The parts of a card every kind shares: title button, story time, wants and feels. */
function CardBody({ event, title, target }: { event?: TimelineEvent; title: string; target: Target }) {
  const { open, move, axis } = useJourney()
  return <>
    <button type="button" className="journey-card-open" onClick={() => open(target)} onKeyDown={keyEvent => moveKey(keyEvent, chosen => move(target, chosen), axis === 'narrative')}>
      {title}
    </button>
    {event && <>
      {event.story_time && <small className="journey-time">{event.story_time}</small>}
      {event.objective && <p><span>Wants</span> {event.objective}</p>}
      {event.emotional_state && <p><span>Feels</span> {event.emotional_state}</p>}
    </>}
  </>
}

/** One character's card, banded by intensity. */
function CardNode({ data }: NodeProps<Node<CardData>>) {
  const { selected, mergeIds, toggleMerge, hoveredScene } = useJourney()
  const { event, ghost } = data.card
  const band = intensityBand(event.intensity)
  const isSelected = selected?.kind === 'event' && selected.id === event.id
  const hot = data.sceneId !== undefined && data.sceneId === hoveredScene
  return <article className={`journey-card band-${band}${ghost ? ' ghost' : ''}${hot ? ' highlight' : ''}${isSelected ? ' selected' : ''}`}
    style={{ width: CARD_WIDTH, height: CARD_HEIGHT }} aria-label={`Card ${event.title}`} data-intensity={event.intensity}>
    <span className="journey-band" aria-hidden="true" />
    <label className="journey-merge nodrag"><input type="checkbox" checked={mergeIds.has(event.id)} onChange={() => toggleMerge(event.id)} /><span className="visually-hidden">Select {event.title} for merge</span></label>
    <CardBody event={event} title={event.title} target={{ kind: 'event', id: event.id }} />
    {ghost && <span className="journey-ghost-badge">Proposed</span>}
  </article>
}

/** A shared moment: drawn once across its lanes, with a connector into each participant's lane. */
function MomentNode({ data }: NodeProps<Node<MomentData>>) {
  const { selected, hoveredScene, open } = useJourney()
  const { item, sides } = data
  const isSelected = selected?.kind === 'moment' && selected.id === item.moment.id
  const hot = data.sceneId !== undefined && data.sceneId === hoveredScene
  return <article className={`journey-moment${item.ghost ? ' ghost' : ''}${hot ? ' highlight' : ''}${isSelected ? ' selected' : ''}`}
    style={{ width: CARD_WIDTH, height: item.height }} aria-label={`Shared moment ${item.moment.title}`}>
    <span className="journey-spine" aria-hidden="true" />
    {sides.map((side, index) => <section key={side.event.id} className={`journey-moment-side band-${intensityBand(side.event.intensity)}`} style={{ top: side.top - item.y, height: CARD_HEIGHT }}>
      <span className="journey-band" aria-hidden="true" />
      {index === 0 && <CardBody title={item.moment.title} target={{ kind: 'moment', id: item.moment.id }} />}
      <button type="button" className="journey-side-open" onClick={() => open({ kind: 'event', id: side.event.id })}>{side.name}</button>
      {side.event.objective && <p><span>Wants</span> {side.event.objective}</p>}
      {side.event.emotional_state && <p><span>Feels</span> {side.event.emotional_state}</p>}
    </section>)}
    {item.ghost && <span className="journey-ghost-badge">Proposed</span>}
  </article>
}

/** The intensity curves: one line per lane inside its band, and the cast average below the lanes. */
function CurveNode({ data }: NodeProps<Node<CurveData>>) {
  return <svg className="journey-curves" width={data.width} height={data.height} aria-hidden="true">
    {data.paths.map(path => <g key={path.name}>
      <path d={path.d} className="journey-curve" />
      {path.dots.map(dot => <circle key={dot.x} cx={dot.x} cy={dot.y} r={3.5} className="journey-curve-dot" />)}
    </g>)}
    {data.cast && <>
      <rect x={HEADER_WIDTH} y={data.castTop} width={data.width - HEADER_WIDTH} height={CAST_HEIGHT - 16} className="journey-cast-band" />
      <line x1={HEADER_WIDTH} x2={data.width} y1={data.castTop + (CAST_HEIGHT - 16) / 2} y2={data.castTop + (CAST_HEIGHT - 16) / 2} className="journey-cast-zero" />
      <path d={data.cast} className="journey-curve cast" />
    </>}
  </svg>
}

const nodeTypes = { lane: LaneHeader, column: ColumnHeader, card: CardNode, moment: MomentNode, curve: CurveNode }

type CanvasProps = {
  layout: JourneyLayout
  actLabels: Map<number, string>
  relationships: Relationship[]
  showCurves: boolean
  showCast: boolean
  showRelationships: boolean
  onDrop: (target: Target, x: number) => void
}

/** Build the canvas nodes for a layout. */
function buildNodes(layout: JourneyLayout, actLabels: Map<number, string>, showCurves: boolean, showCast: boolean): Node[] {
  const nodes: Node[] = []
  const names = new Map(layout.lanes.map(lane => [lane.character.id, lane.character.name]))
  let lastAct: number | null | undefined
  for (const column of layout.columns) {
    const actLabel = column.kind !== 'chrono' && column.actId !== lastAct ? (column.actId === null ? 'No act' : actLabels.get(column.actId)) : undefined
    lastAct = column.actId
    nodes.push({ id: column.key, type: 'column', position: { x: column.x + 6, y: 0 }, data: { label: column.label, moved: column.movedFrom, actLabel, sceneId: column.sceneId }, draggable: false, selectable: false })
  }
  for (const lane of layout.lanes) {
    nodes.push({ id: `lane-${lane.character.id}`, type: 'lane', position: { x: 0, y: lane.y + 4 }, data: { name: lane.character.name, role: lane.character.role, characterId: lane.character.id, height: lane.height }, draggable: false, selectable: false })
  }
  const sceneOf = (column: number) => layout.columns[column]?.sceneId
  for (const card of layout.cards) {
    nodes.push({ id: `event-${card.event.id}`, type: 'card', position: { x: card.x, y: card.y }, data: { card, sceneId: sceneOf(card.column) }, draggable: true, zIndex: 2 })
  }
  for (const item of layout.moments) {
    const sides = item.lanes.flatMap(lane => {
      const event = item.events.find(row => row.character_id === layout.lanes[lane].character.id)
      return event ? [{ event, name: names.get(event.character_id) ?? '', top: layout.lanes[lane].y + LANE_PADDING + item.slot * SLOT_HEIGHT }] : []
    })
    nodes.push({ id: `moment-${item.moment.id}`, type: 'moment', position: { x: item.x, y: item.y }, data: { item, sides, sceneId: sceneOf(item.column) }, draggable: true, zIndex: 2 })
  }
  if (showCurves || showCast) {
    const paths = showCurves ? layout.lanes.map(lane => {
      const points = laneCurve(layout, lane.index)
      const top = lane.y + LANE_PADDING
      const height = lane.height - LANE_PADDING * 2
      return { name: lane.character.name, d: curvePath(points, top, height), dots: points.map(point => ({ x: point.x, y: curveY(point.value, top, height) })) }
    }) : []
    const castTop = layout.height + 8
    const cast = showCast ? curvePath(castCurve(layout), castTop, CAST_HEIGHT - 16) : ''
    nodes.push({ id: 'curves', type: 'curve', position: { x: 0, y: 0 }, data: { paths, cast, width: Math.max(layout.width, HEADER_WIDTH + COLUMN_WIDTH), height: layout.height + CAST_HEIGHT, castTop }, draggable: false, selectable: false, zIndex: 3, style: { pointerEvents: 'none' } })
  }
  return nodes
}

/** The map canvas (React Flow): lanes, columns, cards, moments, curves and relationship edges. */
export default function JourneyCanvas({ layout, actLabels, relationships, showCurves, showCast, showRelationships, onDrop }: CanvasProps) {
  const built = useMemo(() => buildNodes(layout, actLabels, showCurves, showCast), [layout, actLabels, showCurves, showCast])
  const [nodes, setNodes, onNodesChange] = useNodesState(built)
  useEffect(() => setNodes(built), [built, setNodes])
  const edges = useMemo<Edge[]>(() => {
    if (!showRelationships) return []
    const lanes = new Set(layout.lanes.map(lane => lane.character.id))
    return relationships
      .filter(row => lanes.has(row.source_character_id) && lanes.has(row.target_character_id) && row.source_character_id !== row.target_character_id)
      .map(row => ({ id: `rel-${row.id}`, source: `lane-${row.source_character_id}`, sourceHandle: 'out', target: `lane-${row.target_character_id}`, targetHandle: 'in', label: row.relation, type: 'smoothstep', pathOptions: { offset: 28, borderRadius: 10 }, className: 'journey-relationship', selectable: false,
        labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 3, labelBgStyle: { fill: 'var(--surface)' }, labelStyle: { fill: 'var(--ink-soft)' } }))
  }, [layout.lanes, relationships, showRelationships])
  return <div className="journey-canvas" aria-label="Journey map canvas">
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
      onNodeDragStop={(_, node) => {
        const [kind, id] = node.id.split('-')
        if (kind === 'event' || kind === 'moment') onDrop({ kind, id: Number(id) }, node.position.x)
      }}
      nodesConnectable={false} elementsSelectable={false} disableKeyboardA11y fitView fitViewOptions={{ maxZoom: 1, padding: 0.08 }} minZoom={0.15}>
      <Background gap={COLUMN_WIDTH} />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable ariaLabel="Journey map overview" style={{ width: 160, height: 96 }} />
    </ReactFlow>
  </div>
}
