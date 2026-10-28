import { closestCenter, DndContext, type DragEndEvent, PointerSensor, useDraggable, useSensor, useSensors } from '@dnd-kit/core'
import { horizontalListSortingStrategy, SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { KeyboardEvent, ReactNode } from 'react'
import type { Character, StoryMoment, TimelineEvent } from '../storyApi'
import type { SceneLite } from './layout'

/** Format seconds as m:ss. */
export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** Pointer drags start after a short move, so clicks still open and select. */
export function useJourneySensors() {
  return useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
}

/** One scene in the strip: sortable, a drop target for tray cards, highlighted on hover or focus. */
function StripScene({ scene, number, seconds, moved, active, onHover, onSelect, onMove }: {
  scene: SceneLite; number: number; seconds: number; moved?: number; active: boolean
  onHover: (sceneId: number | null) => void; onSelect: () => void; onMove: (delta: -1 | 1) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isOver } = useSortable({ id: `scene-${scene.id}` })
  const keys = (event: KeyboardEvent): void => {
    if (!event.altKey || (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')) return
    event.preventDefault()
    onMove(event.key === 'ArrowLeft' ? -1 : 1)
  }
  return <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition, flexGrow: Math.max(1, Math.round(seconds / 30)) }}
    className={`journey-strip-scene${moved ? ' ghost' : ''}${active ? ' active' : ''}${isOver ? ' over' : ''}`} {...attributes} {...listeners} role="listitem" tabIndex={-1}>
    <button type="button" aria-pressed={active} aria-label={`Scene ${number}: ${scene.heading}`} onClick={onSelect} onKeyDown={keys}
      onMouseEnter={() => onHover(scene.id)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(scene.id)} onBlur={() => onHover(null)}>
      <strong>{number}</strong><span>{scene.heading}</span><small>{clock(seconds)}{moved ? ` · was ${moved}` : ''}</small>
    </button>
  </li>
}

/** The script itself, scene by scene in the order shown: hover to highlight, drag (or Alt+arrows) to propose a reorder. */
export function ScrubStrip({ order, scenes, baseOrder, seconds, selected, onHover, onSelect, onMove }: {
  order: number[]; scenes: Map<number, SceneLite>; baseOrder: number[]; seconds: (sceneId: number) => number; selected: number | null
  onHover: (sceneId: number | null) => void; onSelect: (sceneId: number | null) => void; onMove: (sceneId: number, delta: -1 | 1) => void
}) {
  const total = order.reduce((sum, id) => sum + seconds(id), 0)
  return <section className="journey-strip" aria-label="Script strip">
    <p className="eyebrow warm">SCRIPT · {order.length} scenes · {clock(total)}</p>
    <SortableContext items={order.map(id => `scene-${id}`)} strategy={horizontalListSortingStrategy}>
      <ol role="list">
        {order.map((id, index) => {
          const scene = scenes.get(id)
          if (!scene) return null
          const before = baseOrder.indexOf(id) + 1
          return <StripScene key={id} scene={scene} number={index + 1} seconds={seconds(id)} moved={before !== index + 1 ? before : undefined} active={selected === id}
            onHover={onHover} onSelect={() => onSelect(selected === id ? null : id)} onMove={delta => onMove(id, delta)} />
        })}
      </ol>
    </SortableContext>
  </section>
}

/** A card waiting in the Unplaced tray; in narrative order it can be dragged onto a scene in the strip. */
function TrayCard({ id, title, detail, draggable, children }: { id: string; title: string; detail: string; draggable: boolean; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id, disabled: !draggable })
  return <li ref={setNodeRef} className={`journey-tray-card${isDragging ? ' dragging' : ''}`} style={{ transform: CSS.Translate.toString(transform) }}>
    {draggable && <span className="journey-grip" {...attributes} {...listeners} aria-label={`Drag ${title} onto a scene`}>⠿</span>}
    <strong>{title}</strong><small>{detail}</small>
    <div>{children}</div>
  </li>
}

/** Cards and moments with no place on the current axis. */
export function UnplacedTray({ events, moments, characters, narrative, onOpen, onOpenMoment, onPlace, onPlaceMoment }: {
  events: TimelineEvent[]; moments: StoryMoment[]; characters: Map<number, Character>; narrative: boolean
  onOpen: (eventId: number) => void; onOpenMoment: (momentId: number) => void; onPlace: (eventId: number) => void; onPlaceMoment: (momentId: number) => void
}) {
  const empty = !events.length && !moments.length
  return <section className="journey-tray" aria-label="Unplaced">
    <p className="eyebrow warm">UNPLACED · {events.length + moments.length}</p>
    {empty ? <p className="muted">{narrative ? 'Every card sits in a scene or beat.' : 'Every card has a story-world time.'}</p> : <>
      <p className="muted small">{narrative ? 'Drag a card onto a scene in the strip, or pick its scene in the card.' : 'Place a card at the end of story time, then step it earlier.'}</p>
      <ul>
        {moments.map(moment => <TrayCard key={`m${moment.id}`} id={`moment-${moment.id}`} title={moment.title} detail="Shared moment" draggable={narrative}>
          <button type="button" className="button quiet small" onClick={() => onOpenMoment(moment.id)}>Open<span className="visually-hidden"> {moment.title}</span></button>
          {!narrative && <button type="button" className="button quiet small" onClick={() => onPlaceMoment(moment.id)}>Place on axis<span className="visually-hidden"> {moment.title}</span></button>}
        </TrayCard>)}
        {events.map(event => <TrayCard key={event.id} id={`event-${event.id}`} title={event.title} detail={characters.get(event.character_id)?.name ?? ''} draggable={narrative}>
          <button type="button" className="button quiet small" onClick={() => onOpen(event.id)}>Open<span className="visually-hidden"> {event.title}</span></button>
          {!narrative && <button type="button" className="button quiet small" onClick={() => onPlace(event.id)}>Place on axis<span className="visually-hidden"> {event.title}</span></button>}
        </TrayCard>)}
      </ul>
    </>}
  </section>
}

/** One lane in the cast order list: sortable, with up/down buttons. */
function CastRow({ character, index, count, onMove }: { character: Character; index: number; count: number; onMove: (delta: -1 | 1) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: `lane-${character.id}` })
  return <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className="journey-cast-row">
    <span className="journey-grip" {...attributes} {...listeners} aria-label={`Drag ${character.name}`}>⠿</span>
    <span>{character.name}</span>
    <button type="button" className="button quiet small" aria-label={`Move ${character.name} up`} disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
    <button type="button" className="button quiet small" aria-label={`Move ${character.name} down`} disabled={index === count - 1} onClick={() => onMove(1)}>↓</button>
  </li>
}

/** The lanes' order (the cast's order): drag or use the arrows. */
export function CastOrder({ cast, onReorder }: { cast: Character[]; onReorder: (ids: number[]) => void }) {
  const sensors = useJourneySensors()
  const ids = cast.map(row => row.id)
  const move = (from: number, to: number): void => {
    if (to < 0 || to >= ids.length) return
    const next = [...ids]
    const [id] = next.splice(from, 1)
    next.splice(to, 0, id)
    onReorder(next)
  }
  const end = ({ active, over }: DragEndEvent): void => {
    if (!over || active.id === over.id) return
    move(ids.indexOf(Number(String(active.id).slice(5))), ids.indexOf(Number(String(over.id).slice(5))))
  }
  return <section className="journey-cast" aria-label="Lane order">
    <p className="eyebrow warm">LANES</p>
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={end}>
      <SortableContext items={ids.map(id => `lane-${id}`)} strategy={verticalListSortingStrategy}>
        <ul>{cast.map((character, index) => <CastRow key={character.id} character={character} index={index} count={cast.length} onMove={delta => move(index, index + delta)} />)}</ul>
      </SortableContext>
    </DndContext>
  </section>
}
