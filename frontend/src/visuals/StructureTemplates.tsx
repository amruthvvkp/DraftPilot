import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { errorMessage, keys, useBeats } from '../data/queries'
import { type Beat, storyApi, type StoryVisuals } from '../storyApi'
import ConfirmDialog from '../project/ConfirmDialog'
import { useProjectId } from '../project/useProjectId'
import { matchTemplate, planTemplateBeats, type StructureTemplate, TEMPLATES } from './templates'
import { ToolHead, WithVisuals } from './VisualsLayout'

const percent = (value: number) => `${Math.round(value * 100)}%`

/** Where a writer's beat falls in the runtime (0…1): the start of its earliest linked scene, or null. */
export function beatAt(beat: Beat, visuals: Pick<StoryVisuals, 'scenes' | 'total_runtime_seconds'>): number | null {
  const starts = visuals.scenes.filter(scene => beat.scene_ids.includes(scene.id)).map(scene => scene.start_seconds)
  return starts.length && visuals.total_runtime_seconds ? Math.min(...starts) / visuals.total_runtime_seconds : null
}

/** A template laid over the outline: target beats on a runtime track, matched against the writer's beats. */
function TemplateOverlay({ template, beats, visuals }: { template: StructureTemplate; beats: Beat[]; visuals: StoryVisuals }) {
  const projectId = useProjectId()
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const matches = matchTemplate(template, beats)
  const actIds = [...visuals.acts].sort((a, b) => a.position - b.position).map(act => act.id)
  const plan = planTemplateBeats(matches, beats, actIds)
  const placed = beats.map(beat => ({ beat, at: beatAt(beat, visuals) })).filter((item): item is { beat: Beat; at: number } => item.at !== null)

  async function apply(): Promise<void> {
    setBusy(true)
    setError('')
    let created = 0
    try {
      for (const fields of plan) { await storyApi.createBeat(projectId, fields); created += 1 }
      setDone(`Added ${created} target beat${created === 1 ? '' : 's'} to the outline.`)
    } catch (reason) {
      setError(`${errorMessage(reason, 'Unable to add the beats')}${created ? ` (${created} added before the error)` : ''}`)
    } finally {
      setBusy(false)
      setConfirming(false)
      await queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
      await queryClient.invalidateQueries({ queryKey: keys.visuals(projectId) })
    }
  }

  return <section className="template-overlay" aria-label={`${template.name} overlay`}>
    <div className="template-track" role="img" aria-label={`${template.name}: ${matches.length} target beats, ${matches.length - plan.length} matched`}>
      {template.acts.map((act, index) => <span key={act} className="template-act" style={{ left: percent(template.beats.find(beat => beat.act === index)?.at ?? 0) }}>{act}</span>)}
      {matches.map(match => <span key={match.target.title} className={`template-target${match.beat ? ' matched' : ''}`} style={{ left: percent(match.target.at) }} title={`${match.target.title} · target ${percent(match.target.at)}`} />)}
      {placed.map(item => <span key={item.beat.id} className="template-actual" style={{ left: percent(item.at) }} title={`${item.beat.title} · at ${percent(item.at)}`} />)}
    </div>
    <p className="pacing-legend" aria-hidden="true"><span className="legend-target" />target <span className="legend-target matched" />matched target <span className="legend-actual" />your beat (by its first scene)</p>
    {error && <p className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss">×</button></p>}
    {done && <p className="empty-copy" role="status">{done}</p>}
    <table className="visual-table">
      <caption className="visually-hidden">{template.name} target beats</caption>
      <thead><tr><th scope="col">Target beat</th><th scope="col">Act</th><th scope="col">Target</th><th scope="col">Your beat</th><th scope="col">At</th></tr></thead>
      <tbody>{matches.map(({ target, beat }) => {
        const at = beat ? beatAt(beat, visuals) : null
        return <tr key={target.title} className={beat ? 'matched' : 'missing'}>
          <th scope="row">{target.title}<small>{target.summary}</small></th>
          <td>{template.acts[target.act]}</td><td>{percent(target.at)}</td>
          <td>{beat ? beat.title : <em>Missing</em>}</td><td>{at === null ? '—' : percent(at)}</td>
        </tr>
      })}</tbody>
    </table>
    <button type="button" className="button primary" disabled={!plan.length || busy} onClick={() => setConfirming(true)}>
      {plan.length ? `Add ${plan.length} missing beat${plan.length === 1 ? '' : 's'} to the outline` : 'Every target beat is covered'}
    </button>
    {confirming && <ConfirmDialog title={`Add ${plan.length} ${template.name} beats?`} confirmLabel="Add beats" busy={busy} onCancel={() => setConfirming(false)} onConfirm={() => void apply()}>
      <p>These planned beats will be added to your outline. You can edit, move or delete them there.</p>
      <ul className="template-plan">{plan.map(fields => <li key={fields.title}>{fields.title} <small>→ {visuals.acts.find(act => act.id === fields.act_id)?.title ?? 'Unassigned'}</small></li>)}</ul>
    </ConfirmDialog>}
  </section>
}

/** The structure templates page: pick Save the Cat, the Hero’s Journey or five acts and see it over the outline. */
export default function StructureTemplatesPage() {
  const projectId = useProjectId()
  const [chosen, setChosen] = useState(TEMPLATES[0].id)
  const { data: beats, error } = useBeats(projectId)
  const template = TEMPLATES.find(item => item.id === chosen) ?? TEMPLATES[0]
  return <>
    <ToolHead title="Structure templates">Lay a classic structure over your outline as target beats. Targets sit at their usual share of the runtime; your beats sit where their first linked scene starts. Nothing changes until you choose to add the missing beats.</ToolHead>
    <div className="template-picker" role="radiogroup" aria-label="Structure template">
      {TEMPLATES.map(item => <label key={item.id} className={item.id === chosen ? 'choice on' : 'choice'}>
        <input type="radio" name="template" value={item.id} checked={item.id === chosen} onChange={() => setChosen(item.id)} />{item.name}
      </label>)}
    </div>
    {error && <p className="notice" role="alert">{errorMessage(error, 'Unable to load the beats')}</p>}
    <WithVisuals>{visuals => beats ? <TemplateOverlay key={template.id} template={template} beats={beats} visuals={visuals} /> : <p className="empty-copy">Loading…</p>}</WithVisuals>
  </>
}
