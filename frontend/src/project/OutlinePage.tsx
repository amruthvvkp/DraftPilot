import { type FormEvent, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Act } from '../api'
import { errorMessage, keys, useBeats, useCharacters, useWorkspace } from '../data/queries'
import { type Beat, type BeatFields, storyApi } from '../storyApi'
import { ActHeader, AddBeatForm } from './ActColumn'
import BeatCard, { type BeatMoves } from './BeatCard'
import ConfirmDialog from './ConfirmDialog'
import { beatsIn, planBeatMove } from './outlinePlan'
import { useProjectId } from './useProjectId'

const actName = (act: Act) => act.title || `Act ${act.position + 1}`

function DeleteActDialog({ act, acts, sceneCount, onCancel, onConfirm }: { act: Act; acts: Act[]; sceneCount: number; onCancel: () => void; onConfirm: (moveTo?: number) => void }) {
  const others = acts.filter(item => item.id !== act.id)
  const [target, setTarget] = useState(others[0]?.id ?? 0)
  return <ConfirmDialog title={`Delete ${actName(act)}?`} confirmLabel="Delete act" onCancel={onCancel} onConfirm={() => onConfirm(sceneCount ? target : undefined)}>
    <p>Its beats move to “Unassigned”.{sceneCount ? ` Its ${sceneCount} scene${sceneCount === 1 ? '' : 's'} move to the act you choose.` : ''}</p>
    {sceneCount > 0 && <label>Move its scenes to<select value={target} onChange={event => setTarget(Number(event.target.value))}>
      {others.map(item => <option key={item.id} value={item.id}>{actName(item)}</option>)}
    </select></label>}
  </ConfirmDialog>
}

/** The outline: any number of acts, each holding beats you can drag, reorder, link to scenes and characters, and turn into scenes. */
export default function OutlinePage() {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const { data: workspace, error: workspaceError } = useWorkspace(projectId)
  const { data: beatList, error: beatsError } = useBeats(projectId)
  const characters = useCharacters(projectId).data ?? []
  const [error, setError] = useState('')
  const [newAct, setNewAct] = useState('')
  const [deletingAct, setDeletingAct] = useState<Act | null>(null)
  const [deletingBeat, setDeletingBeat] = useState<Beat | null>(null)
  const dragging = useRef<number | null>(null)

  const acts = [...(workspace?.acts ?? [])].sort((a, b) => a.position - b.position)
  const actIds = new Set(acts.map(act => act.id))
  const beats = beatList ?? []
  const scenes = workspace?.scenes ?? []
  const unassigned = beatsIn(beats, null, actIds)
  const columns: (Act | null)[] = [...acts, ...(unassigned.length ? [null] : [])]

  const refreshBeats = () => queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
  const refreshStructure = () => queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })

  async function run(change: () => Promise<unknown>, fallback: string): Promise<boolean> {
    setError('')
    try { await change(); return true } catch (reason) { setError(errorMessage(reason, fallback)); return false }
  }

  // Beat writes run one at a time, each against the freshest cached version, so quick edits never race into a 409.
  const writes = useRef<Promise<unknown>>(Promise.resolve())
  const latest = (beatId: number) => queryClient.getQueryData<Beat[]>(keys.beats(projectId))?.find(item => item.id === beatId)
  function storeBeat(saved: Beat): void {
    queryClient.setQueryData<Beat[]>(keys.beats(projectId), current => current?.map(item => item.id === saved.id ? saved : item))
  }
  function enqueue(change: () => Promise<unknown>, fallback: string): Promise<boolean> {
    const next = writes.current.then(() => run(change, fallback))
    writes.current = next
    return next
  }

  function saveBeat(beat: Beat, fields: BeatFields): void {
    void enqueue(async () => storeBeat(await storyApi.updateBeat(projectId, latest(beat.id) ?? beat, fields)), 'Unable to save the beat')
      .then(ok => { if (!ok) void refreshBeats() })
  }

  function moveBeat(beatId: number, actId: number | null, index: number): void {
    void enqueue(async () => {
      const current = queryClient.getQueryData<Beat[]>(keys.beats(projectId)) ?? beats
      for (const change of planBeatMove(current, beatId, actId, index, actIds)) storeBeat(await storyApi.updateBeat(projectId, change.beat, change.fields))
    }, 'Unable to move the beat').then(() => refreshBeats())
  }

  function movesFor(beat: Beat, column: number | null, index: number, count: number): BeatMoves {
    const at = column === null ? -1 : acts.findIndex(act => act.id === column)
    const previous = column === null ? acts[acts.length - 1] : acts[at - 1]
    const next = column === null ? undefined : acts[at + 1]
    return {
      earlier: index > 0 ? () => moveBeat(beat.id, column, index - 1) : undefined,
      later: index < count - 1 ? () => moveBeat(beat.id, column, index + 1) : undefined,
      previousAct: previous ? () => moveBeat(beat.id, previous.id, beatsIn(beats, previous.id, actIds).length) : undefined,
      nextAct: next ? () => moveBeat(beat.id, next.id, beatsIn(beats, next.id, actIds).length) : undefined,
    }
  }

  async function addBeat(actId: number | null, title: string): Promise<void> {
    const position = beatsIn(beats, actId, actIds).length
    await run(() => storyApi.createBeat(projectId, { title, act_id: actId, position }), 'Unable to add the beat')
    await refreshBeats()
  }

  async function createSceneFromBeat(beat: Beat, heading: string): Promise<void> {
    const actId = beat.act_id !== null && actIds.has(beat.act_id) ? beat.act_id : undefined
    await enqueue(async () => {
      const scene = await storyApi.createScene(projectId, heading, { actId, screenplayId: workspace?.screenplay?.id })
      const current = latest(beat.id) ?? beat
      storeBeat(await storyApi.updateBeat(projectId, current, { scene_ids: [...current.scene_ids, scene.id] }))
    }, 'Unable to create the scene')
    await Promise.all([refreshBeats(), refreshStructure()])
  }

  async function addAct(event: FormEvent): Promise<void> {
    event.preventDefault()
    const ok = await run(() => storyApi.createAct(projectId, newAct.trim(), workspace?.screenplay?.id), 'Unable to add the act')
    if (ok) setNewAct('')
    await refreshStructure()
  }

  async function changeAct(change: () => Promise<unknown>, fallback: string): Promise<void> {
    await run(change, fallback)
    await Promise.all([refreshStructure(), refreshBeats()])
  }

  function drop(column: number | null, index: number): void {
    const beatId = dragging.current
    dragging.current = null
    if (beatId !== null) moveBeat(beatId, column, index)
  }

  const loadError = workspaceError || beatsError
  return <main className="story-page outline-page">
    <header className="story-head">
      <p className="eyebrow warm">STEP 3 · OUTLINE</p>
      <h1>Outline</h1>
      <p>Acts and the beats inside them. Drag beats, or focus a beat’s handle and use the arrow keys. Link beats to scenes and characters, or create a scene straight from a beat.</p>
      <form className="story-inline-form" aria-label="New act" onSubmit={event => void addAct(event)}>
        <input aria-label="New act title" placeholder={`Act ${acts.length + 1}`} value={newAct} onChange={event => setNewAct(event.target.value)} />
        <button className="button quiet" type="submit" disabled={!workspace?.screenplay}>Add act</button>
      </form>
    </header>
    {(error || loadError) && <p className="notice" role="alert">{error || errorMessage(loadError, 'Unable to load the outline')}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    <datalist id="screenplay-headings"><option value="INT. - DAY" /><option value="INT. - NIGHT" /><option value="EXT. - DAY" /><option value="EXT. - NIGHT" /></datalist>
    <div className="outline-board" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(240px, 1fr))` }}>
      {columns.map((act, columnIndex) => {
        const column = act?.id ?? null
        const name = act ? actName(act) : 'Unassigned'
        const list = beatsIn(beats, column, actIds)
        return <section key={column ?? 'unassigned'} className="beat-column" aria-label={name}
          onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); drop(column, list.length) }}>
          {act ? <ActHeader act={act} name={name} canMoveEarlier={columnIndex > 0} canMoveLater={columnIndex < acts.length - 1}
            onRename={title => void changeAct(() => storyApi.updateAct(projectId, act.id, { title }), 'Unable to rename the act')}
            onMove={delta => void changeAct(() => storyApi.updateAct(projectId, act.id, { position: act.position + delta }), 'Unable to move the act')}
            onDelete={() => setDeletingAct(act)} /> : <p className="eyebrow">UNASSIGNED</p>}
          <small className="act-count">{list.length} beats · {scenes.filter(scene => scene.act_id === column).length} scenes</small>
          {list.map((beat, index) => <BeatCard key={beat.id} projectId={projectId} beat={beat} scenes={scenes} characters={characters}
            moves={movesFor(beat, column, index, list.length)} onSave={fields => saveBeat(beat, fields)} onDelete={() => setDeletingBeat(beat)}
            onCreateScene={heading => createSceneFromBeat(beat, heading)} onDragStart={() => { dragging.current = beat.id }} onDropHere={() => drop(column, index)} />)}
          <AddBeatForm columnName={name} onAdd={title => addBeat(column, title)} />
        </section>
      })}
    </div>
    {workspace && acts.length === 0 && <p className="empty-copy">This draft has no acts yet. Add one above.</p>}
    {deletingAct && <DeleteActDialog act={deletingAct} acts={acts} sceneCount={scenes.filter(scene => scene.act_id === deletingAct.id).length}
      onCancel={() => setDeletingAct(null)}
      onConfirm={moveTo => { const act = deletingAct; setDeletingAct(null); void changeAct(() => storyApi.deleteAct(projectId, act.id, moveTo), 'Unable to delete the act') }} />}
    {deletingBeat && <ConfirmDialog title={`Delete beat “${deletingBeat.title}”?`} confirmLabel="Delete beat" onCancel={() => setDeletingBeat(null)}
      onConfirm={() => { const beat = deletingBeat; setDeletingBeat(null); void run(() => storyApi.deleteBeat(projectId, beat), 'Unable to delete the beat').then(() => refreshBeats()) }}>
      <p>Linked scenes stay in the script.</p>
    </ConfirmDialog>}
  </main>
}
