import { closestCenter, DndContext, type DragEndEvent } from '@dnd-kit/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { errorMessage, keys, useBeats, useCharacters, useMoments, useRelationships, useTimeline, useVariants, useWorkspace } from '../data/queries'
import { persistPositions } from '../project/order'
import { beatsIn, planBeatMove } from '../project/outlinePlan'
import { useProjectId } from '../project/useProjectId'
import { type Beat, type StoryMomentFields, storyApi, type TimelineEvent, type TimelineEventFields } from '../storyApi'
import { EventPanel, MomentPanel } from './CardPanel'
import JourneyCanvas, { type JourneyActions, JourneyContext, type Move, type Target } from './JourneyCanvas'
import {
  type Axis, CARD_WIDTH, chronoAt, columnAt, COLUMN_WIDTH, HEADER_WIDTH, type JourneyData, type JourneyLayout, layoutJourney, mergeCandidates,
  moveSceneInAct, moveSceneTo, orderedCast, scriptOrder, stepChrono,
} from './layout'
import { CastOrder, ScrubStrip, UnplacedTray, useJourneySensors } from './Rails'
import { fitOrder, sceneSeconds, useSceneReorder } from './useSceneReorder'
import './journey.css'

/** Every story-world position on the map except the target's own. */
function otherChronos(layout: JourneyLayout, target: Target): number[] {
  const values: number[] = []
  for (const card of layout.cards) if (!(target.kind === 'event' && card.event.id === target.id) && card.event.chrono_index !== null) values.push(card.event.chrono_index)
  for (const item of layout.moments) if (!(target.kind === 'moment' && item.moment.id === target.id) && item.moment.chrono_index !== null) values.push(item.moment.chrono_index)
  return [...new Set(values)].sort((a, b) => a - b)
}

/** The Journey map: character swimlanes on a narrative or chronology axis, shared moments, curves and safe reordering. */
export default function JourneyPage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const workspace = useWorkspace(projectId).data
  const characters = useCharacters(projectId).data
  const events = useTimeline(projectId).data
  const moments = useMoments(projectId).data
  const beats = useBeats(projectId).data
  const relationships = useRelationships(projectId).data ?? []
  const variants = useVariants(projectId).data ?? []
  const [axis, setAxis] = useState<Axis>('narrative')
  const [laneOrder, setLaneOrder] = useState<number[] | undefined>()
  const [selected, setSelected] = useState<Target | null>(null)
  const [mergeIds, setMergeIds] = useState<Set<number>>(new Set())
  const [hoveredScene, setHoveredScene] = useState<number | null>(null)
  const [stripScene, setStripScene] = useState<number | null>(null)
  const [showCurves, setShowCurves] = useState(true)
  const [showCast, setShowCast] = useState(false)
  const [showRelationships, setShowRelationships] = useState(true)
  const [variantName, setVariantName] = useState('')
  const [variantId, setVariantId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const sensors = useJourneySensors()

  const acts = useMemo(() => [...(workspace?.acts ?? [])].sort((a, b) => a.position - b.position), [workspace?.acts])
  const scenes = useMemo(() => (workspace?.scenes ?? []).map(({ id, act_id, heading, position }) => ({ id, act_id, heading, position })), [workspace?.scenes])
  const baseOrder = useMemo(() => scriptOrder(acts, scenes), [acts, scenes])
  const reorder = useSceneReorder(projectId, workspace, baseOrder)
  const data: JourneyData = useMemo(() => ({ characters: characters ?? [], events: events ?? [], moments: moments ?? [], acts, scenes, beats: beats ?? [] }), [characters, events, moments, acts, scenes, beats])
  const order = axis === 'narrative' ? reorder.order : baseOrder
  const layout = useMemo(() => layoutJourney(data, axis, { order, baseOrder, laneOrder }), [data, axis, order, baseOrder, laneOrder])
  const actLabels = useMemo(() => new Map(acts.map(act => [act.id, act.title || `Act ${act.position + 1}`])), [acts])
  const actOf = useMemo(() => new Map(scenes.map(scene => [scene.id, scene.act_id])), [scenes])
  const sceneById = useMemo(() => new Map(scenes.map(scene => [scene.id, scene])), [scenes])
  const characterById = useMemo(() => new Map((characters ?? []).map(row => [row.id, row])), [characters])
  const candidates = useMemo(() => mergeCandidates(data.events, scenes, data.beats), [data.events, scenes, data.beats])

  /** Run a write, report failures (409s explain themselves), then refetch what it touched. */
  async function write(action: () => Promise<unknown>, fallback: string, touched: readonly (readonly unknown[])[] = [keys.timelines(projectId), keys.moments(projectId)]): Promise<boolean> {
    setError('')
    let ok = true
    try {
      await action()
    } catch (reason) {
      setError(errorMessage(reason, fallback))
      ok = false
    }
    await Promise.all(touched.map(queryKey => queryClient.invalidateQueries({ queryKey })))
    return ok
  }

  const latestEvent = (id: number): TimelineEvent | undefined => queryClient.getQueryData<TimelineEvent[]>(keys.timeline(projectId))?.find(row => row.id === id) ?? data.events.find(row => row.id === id)
  const saveEvent = (id: number, fields: TimelineEventFields) => write(async () => {
    const row = latestEvent(id)
    if (row) await storyApi.updateEvent(projectId, row, fields)
  }, 'Unable to save the card')
  const saveMoment = (id: number, fields: StoryMomentFields) => write(async () => {
    const row = data.moments.find(item => item.id === id)
    if (row) await storyApi.updateMoment(projectId, row, fields)
  }, 'Unable to save the moment')

  /** Where a target sits on the current layout (its column), if anywhere. */
  function columnOf(target: Target): number | null {
    if (target.kind === 'event') return layout.cards.find(card => card.event.id === target.id)?.column ?? null
    return layout.moments.find(item => item.moment.id === target.id)?.column ?? null
  }

  function proposeOrder(next: number[] | null, why: string): void {
    if (!next) { setNotice(why); return }
    setNotice('')
    void reorder.propose(next)
  }

  /** Move a beat with the Outline's plan: contiguous positions, versioned PATCHes. */
  function moveBeat(beatId: number, actId: number | null, index: number): void {
    const actIds = new Set(acts.map(act => act.id))
    void write(async () => {
      const current = queryClient.getQueryData<Beat[]>(keys.beats(projectId)) ?? data.beats
      for (const change of planBeatMove(current, beatId, actId, index, actIds)) await storyApi.updateBeat(projectId, change.beat, change.fields)
    }, 'Unable to move the beat', [keys.beats(projectId)])
  }

  /** The keyboard (and button) equivalent of every card drag. */
  function move(target: Target, chosen: Move): void {
    setNotice('')
    if (axis === 'chronology') {
      if (chosen !== 'earlier' && chosen !== 'later') return
      const current = target.kind === 'event' ? latestEvent(target.id)?.chrono_index ?? null : data.moments.find(row => row.id === target.id)?.chrono_index ?? null
      const value = stepChrono(otherChronos(layout, target), current, chosen === 'earlier' ? -1 : 1)
      if (value === null) { setNotice(chosen === 'earlier' ? 'Already the earliest in story time.' : 'Already the latest in story time.'); return }
      void (target.kind === 'event' ? saveEvent(target.id, { chrono_index: value }) : saveMoment(target.id, { chrono_index: value }))
      return
    }
    const index = columnOf(target)
    const column = index === null ? undefined : layout.columns[index]
    if (!column) { setNotice('Place this card in a scene or beat first.'); return }
    if (column.sceneId !== undefined) {
      if (chosen === 'previous-act' || chosen === 'next-act') { setNotice('A scene keeps its act; move it between acts in the Outline.'); return }
      proposeOrder(moveSceneInAct(order, column.sceneId, chosen === 'earlier' ? -1 : 1, actOf), chosen === 'earlier' ? 'Already the first scene in its act.' : 'Already the last scene in its act.')
      return
    }
    if (column.beatId === undefined) return
    const actIds = new Set(acts.map(act => act.id))
    const beat = data.beats.find(row => row.id === column.beatId)
    if (!beat) return
    const siblings = beatsIn(data.beats, column.actId, actIds)
    const at = siblings.findIndex(row => row.id === beat.id)
    const actIndex = column.actId === null ? acts.length : acts.findIndex(act => act.id === column.actId)
    if (chosen === 'earlier' && at > 0) moveBeat(beat.id, column.actId, at - 1)
    else if (chosen === 'later' && at < siblings.length - 1) moveBeat(beat.id, column.actId, at + 1)
    else if (chosen === 'previous-act' && actIndex > 0) moveBeat(beat.id, acts[actIndex - 1].id, beatsIn(data.beats, acts[actIndex - 1].id, actIds).length)
    else if (chosen === 'next-act' && actIndex < acts.length - 1) moveBeat(beat.id, acts[actIndex + 1].id, 0)
    else setNotice('The beat can’t move further that way.')
  }

  /** A card dropped on the canvas at `x`: reorder its scene or beat (narrative) or retime it (chronology). */
  function drop(target: Target, x: number): void {
    setNotice('')
    const from = columnOf(target)
    if (from === null || !layout.columns.length) return
    if (axis === 'chronology') {
      const center = x + CARD_WIDTH / 2
      const position = (center - HEADER_WIDTH) / COLUMN_WIDTH
      const slot = Math.floor(position)
      const fraction = position - slot
      const values = layout.columns.map(column => column.chrono ?? 0)
      let value: number
      if (fraction >= 0.3 && fraction <= 0.7 && slot >= 0 && slot < values.length) value = values[slot]
      else value = chronoAt(values, Math.max(0, Math.min(values.length, fraction < 0.3 ? slot : slot + 1)))
      const current = layout.columns[from].chrono
      if (value === current) return
      void (target.kind === 'event' ? saveEvent(target.id, { chrono_index: value }) : saveMoment(target.id, { chrono_index: value }))
      return
    }
    const to = columnAt(layout, x)
    if (to === from) return
    const source = layout.columns[from]
    const destination = layout.columns[to]
    if (source.sceneId !== undefined) {
      const nearest = destination.sceneId ?? [...layout.columns].sort((a, b) => Math.abs(a.index - to) - Math.abs(b.index - to)).find(column => column.sceneId !== undefined)?.sceneId
      if (nearest !== undefined) proposeOrder(moveSceneTo(order, source.sceneId, nearest, actOf), 'A scene keeps its act; move it between acts in the Outline.')
      return
    }
    if (source.beatId !== undefined) {
      const index = layout.columns.filter(column => column.beatId !== undefined && column.beatId !== source.beatId && column.actId === destination.actId && column.index < to).length
      moveBeat(source.beatId, destination.actId, index)
    }
  }

  /** Strip and tray drops: reorder scenes, or link an unplaced card to a scene. */
  function stripDrop({ active, over }: DragEndEvent): void {
    if (!over) return
    const [kind, raw] = String(active.id).split('-')
    const sceneId = Number(String(over.id).replace('scene-', ''))
    if (!String(over.id).startsWith('scene-')) return
    if (kind === 'scene' && Number(raw) !== sceneId) proposeOrder(moveSceneTo(order, Number(raw), sceneId, actOf), 'A scene keeps its act; move it between acts in the Outline.')
    if (kind === 'event') void saveEvent(Number(raw), { scene_id: sceneId })
    if (kind === 'moment') void saveMoment(Number(raw), { scene_id: sceneId })
  }

  /** Add a card in a lane and open it; on the chronology axis it starts at the end of story time. */
  function addCard(characterId: number): void {
    const chrono = axis === 'chronology' ? chronoAt(layout.columns.map(column => column.chrono ?? 0), layout.columns.length) : null
    void write(async () => {
      const row = await storyApi.createEvent(projectId, { character_id: characterId, title: 'New card', chrono_index: chrono, position: data.events.filter(item => item.character_id === characterId).length })
      setSelected({ kind: 'event', id: row.id })
    }, 'Unable to add the card')
  }

  /** Merge the selected cards into one shared moment — only ever on the writer's explicit click. */
  function merge(): void {
    const rows = data.events.filter(row => mergeIds.has(row.id))
    if (new Set(rows.map(row => row.character_id)).size < 2) { setNotice('Select cards from at least two characters to merge.'); return }
    void write(async () => {
      let moment = data.moments.find(row => rows.some(event => event.moment_id === row.id))
      if (!moment) {
        const dated = rows.map(row => row.chrono_index).filter((value): value is number => value !== null)
        moment = await storyApi.createMoment(projectId, {
          title: rows[0].title, summary: rows[0].description, story_time: rows.find(row => row.story_time)?.story_time ?? '',
          chrono_index: dated.length ? Math.min(...dated) : null,
          scene_id: rows.find(row => row.scene_id !== null)?.scene_id ?? null, beat_id: rows.find(row => row.beat_id !== null)?.beat_id ?? null,
        })
      }
      for (const row of rows) if (row.moment_id !== moment.id) await storyApi.updateEvent(projectId, row, { moment_id: moment.id })
      setMergeIds(new Set())
      setSelected({ kind: 'moment', id: moment.id })
    }, 'Unable to merge into a shared moment')
  }

  function reorderLanes(ids: number[]): void {
    setLaneOrder(ids)
    const rows = ids.map(id => characterById.get(id)).filter(row => row !== undefined)
    void write(() => persistPositions(rows, (row, position) => storyApi.updateCharacter(projectId, row, { position })), 'Unable to reorder the lanes', [keys.characters(projectId)])
  }

  function placeOnAxis(target: Target): void {
    const value = chronoAt(layout.columns.map(column => column.chrono ?? 0), layout.columns.length)
    void (target.kind === 'event' ? saveEvent(target.id, { chrono_index: value }) : saveMoment(target.id, { chrono_index: value }))
  }

  function saveVariant(formEvent: FormEvent): void {
    formEvent.preventDefault()
    const name = variantName.trim()
    if (!name) return
    void write(() => storyApi.createVariant(projectId, { name, scene_ids: reorder.order }), 'Unable to save the variant', [keys.variants(projectId)]).then(ok => {
      if (ok) { setVariantName(''); setNotice(`Saved “${name}”.`) }
    })
  }

  const variant = variants.find(row => String(row.id) === variantId)
  const actions: JourneyActions = {
    axis, selected, mergeIds, hoveredScene,
    open: target => setSelected(target),
    toggleMerge: id => setMergeIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }),
    move, addCard,
  }

  if (!characters || !events || !moments || !beats || !workspace) return <section className="journey-page" aria-label="Journey map"><p className="muted">Loading the journey map…</p></section>
  const cast = orderedCast(characters, laneOrder)
  const selectedEvent = selected?.kind === 'event' ? data.events.find(row => row.id === selected.id) : undefined
  const selectedMoment = selected?.kind === 'moment' ? data.moments.find(row => row.id === selected.id) : undefined
  const narrative = axis === 'narrative'
  const panelCommon = { projectId, scenes: baseOrder.map(id => sceneById.get(id)!).filter(Boolean), beats: data.beats, narrative, onClose: () => setSelected(null) }

  /** The side panel for the selected card or moment. */
  function renderPanel() {
    if (selectedEvent) {
      const moment = selectedEvent.moment_id !== null ? data.moments.find(row => row.id === selectedEvent.moment_id) : undefined
      const target: Target = moment ? { kind: 'moment', id: moment.id } : { kind: 'event', id: selectedEvent.id }
      return <EventPanel key={`e${selectedEvent.id}-${selectedEvent.version}`} {...panelCommon} event={selectedEvent} character={characterById.get(selectedEvent.character_id)} moment={moment}
        onSave={fields => void saveEvent(selectedEvent.id, fields)} onLeaveMoment={() => void saveEvent(selectedEvent.id, { moment_id: null })} onMove={chosen => move(target, chosen)} />
    }
    if (selectedMoment) {
      return <MomentPanel key={`m${selectedMoment.id}-${selectedMoment.version}`} {...panelCommon} moment={selectedMoment} characters={characterById}
        participants={data.events.filter(row => row.moment_id === selectedMoment.id)} onSave={fields => void saveMoment(selectedMoment.id, fields)}
        onDelete={() => void write(() => storyApi.deleteMoment(projectId, selectedMoment), 'Unable to dissolve the moment').then(() => setSelected(null))}
        onOpen={id => setSelected({ kind: 'event', id })} onMove={chosen => move({ kind: 'moment', id: selectedMoment.id }, chosen)} />
    }
    return null
  }

  return <JourneyContext.Provider value={actions}>
    <section className="journey-page" aria-label="Journey map">
      <header className="journey-head">
        <div><p className="eyebrow warm">JOURNEY MAP</p><h1>Who goes through what, and when.</h1>
          <p className="muted">{narrative ? 'Narrative order: when the audience sees it. Drags propose a reorder; nothing moves until you apply it.' : 'Chronology: when it happens in the story world. Drags change a card’s story time directly.'}</p></div>
        <div className="journey-toolbar">
          <div className="segmented" role="group" aria-label="Axis">
            <button type="button" aria-pressed={narrative} className={narrative ? 'active' : ''} onClick={() => setAxis('narrative')}>Narrative</button>
            <button type="button" aria-pressed={!narrative} className={!narrative ? 'active' : ''} onClick={() => setAxis('chronology')}>Chronology</button>
          </div>
          <label><input type="checkbox" checked={showCurves} onChange={() => setShowCurves(value => !value)} /> Intensity curves</label>
          <label><input type="checkbox" checked={showCast} onChange={() => setShowCast(value => !value)} /> Cast overlay</label>
          <label><input type="checkbox" checked={showRelationships} onChange={() => setShowRelationships(value => !value)} /> Relationships</label>
        </div>
      </header>
      {(error || reorder.error) && <div className="notice" role="alert">{error || reorder.error}</div>}
      {notice && <p className="journey-notice" role="status">{notice}</p>}

      {!characters.length ? <p className="journey-empty">Add characters first — each one gets a lane. <Link to={`/projects/${projectId}/characters`}>Go to Characters</Link></p> : <>
        {(mergeIds.size > 0 || candidates.length > 0) && <section className="journey-merge-bar" aria-label="Shared moments">
          {mergeIds.size > 0 && <>
            <span>{mergeIds.size} selected</span>
            <button type="button" className="button primary small" onClick={merge} disabled={mergeIds.size < 2}>Merge into a shared moment</button>
            <button type="button" className="button quiet small" onClick={() => setMergeIds(new Set())}>Clear selection</button>
          </>}
          {candidates.map(candidate => <span key={candidate.key} className="journey-candidate">
            {candidate.eventIds.length} cards share “{candidate.label}”
            <button type="button" className="button quiet small" onClick={() => setMergeIds(new Set(candidate.eventIds))}>Select them<span className="visually-hidden"> ({candidate.label})</span></button>
          </span>)}
        </section>}

        {narrative && <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={stripDrop}>
          <section className="journey-reorder" aria-label="Narrative order">
            {reorder.pending ? <div className="journey-proposal" role="status">
              <span><strong>Proposed order.</strong> Moved scenes show as ghosts; the script is unchanged until you apply it. {Math.round(reorder.pending.total_runtime_seconds / 60)} min projected.</span>
              <button type="button" className="button primary small" disabled={reorder.busy} onClick={() => void reorder.apply(reorder.pending!)}>Apply reorder</button>
              <button type="button" className="button quiet small" disabled={reorder.busy} onClick={() => void reorder.discard(reorder.pending!)}>Discard</button>
            </div> : reorder.applied ? <div className="journey-proposal applied" role="status">
              <span>Reorder applied.</span>
              <button type="button" className="button quiet small" disabled={reorder.busy} onClick={() => void reorder.rollback(reorder.applied!)}>Roll back</button>
            </div> : null}
            {stripScene !== null && <div className="journey-strip-moves" role="group" aria-label="Move selected scene">
              <span>Scene {order.indexOf(stripScene) + 1} selected</span>
              <button type="button" className="button quiet small" onClick={() => proposeOrder(moveSceneInAct(order, stripScene, -1, actOf), 'Already the first scene in its act.')}>Move scene earlier</button>
              <button type="button" className="button quiet small" onClick={() => proposeOrder(moveSceneInAct(order, stripScene, 1, actOf), 'Already the last scene in its act.')}>Move scene later</button>
            </div>}
            <div className="journey-variants">
              <form onSubmit={saveVariant}>
                <label>Variant name<input value={variantName} onChange={change => setVariantName(change.target.value)} placeholder="Cold open on the funeral" /></label>
                <button type="submit" className="button quiet small" disabled={!variantName.trim() || !order.length}>Save as variant</button>
              </form>
              {variants.length > 0 && <div className="journey-variant-pick">
                <label>Variants<select value={variantId} onChange={change => setVariantId(change.target.value)}>
                  <option value="">Choose a variant</option>
                  {variants.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
                </select></label>
                <button type="button" className="button quiet small" disabled={!variant} onClick={() => variant && proposeOrder(fitOrder(variant.scene_ids, baseOrder), '')}>Propose variant</button>
                <button type="button" className="button quiet small" disabled={!variant} onClick={() => variant && void write(() => storyApi.deleteVariant(projectId, variant), 'Unable to delete the variant', [keys.variants(projectId)]).then(() => setVariantId(''))}>Delete variant</button>
              </div>}
            </div>
          </section>
          {order.length > 0 && <ScrubStrip order={order} scenes={sceneById} baseOrder={baseOrder} seconds={id => sceneSeconds(workspace, id)} selected={stripScene}
            onHover={setHoveredScene} onSelect={setStripScene} onMove={(id, delta) => proposeOrder(moveSceneInAct(order, id, delta, actOf), delta < 0 ? 'Already the first scene in its act.' : 'Already the last scene in its act.')} />}
          <div className="journey-body">
            <div className="journey-side">
              <CastOrder cast={cast} onReorder={reorderLanes} />
              <UnplacedTray events={layout.unplaced} moments={layout.unplacedMoments} characters={characterById} narrative
                onOpen={id => setSelected({ kind: 'event', id })} onOpenMoment={id => setSelected({ kind: 'moment', id })} onPlace={() => undefined} onPlaceMoment={() => undefined} />
            </div>
            <JourneyCanvas layout={layout} actLabels={actLabels} relationships={relationships} showCurves={showCurves} showCast={showCast} showRelationships={showRelationships} onDrop={drop} />
            {renderPanel()}
          </div>
        </DndContext>}

        {!narrative && <div className="journey-body">
          <div className="journey-side">
            <CastOrder cast={cast} onReorder={reorderLanes} />
            <UnplacedTray events={layout.unplaced} moments={layout.unplacedMoments} characters={characterById} narrative={false}
              onOpen={id => setSelected({ kind: 'event', id })} onOpenMoment={id => setSelected({ kind: 'moment', id })}
              onPlace={id => placeOnAxis({ kind: 'event', id })} onPlaceMoment={id => placeOnAxis({ kind: 'moment', id })} />
          </div>
          <JourneyCanvas layout={layout} actLabels={actLabels} relationships={relationships} showCurves={showCurves} showCast={showCast} showRelationships={showRelationships} onDrop={drop} />
          {renderPanel()}
        </div>}
      </>}
    </section>
  </JourneyContext.Provider>
}
