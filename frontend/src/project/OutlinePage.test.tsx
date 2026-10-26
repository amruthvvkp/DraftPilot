import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Beat } from '../storyApi'
import { beat, type Call, character, mockApi, renderAt, workspace } from '../test/harness'
import { planBeatMove } from './outlinePlan'

type Row = Beat & Record<string, unknown>

function outlineBackend() {
  const acts = [{ id: 4, screenplay_id: 12, title: 'Act One', position: 0 }, { id: 5, screenplay_id: 12, title: 'Act Two', position: 1 }]
  const scenes: Record<string, unknown>[] = []
  const beats = [beat(1, 'Wedding toast', 4, 0), beat(2, 'The witch', 4, 1), beat(3, 'Spectre', 5, 0)] as Row[]
  let nextId = 50
  const patchBeat = (call: Call) => {
    const row = beats.find(item => item.id === Number(call.path.split('/').pop()))!
    if (call.headers.get('If-Match') !== String(row.version)) return { status: 409, body: { detail: 'Beat has changed' } }
    Object.assign(row, call.body, { version: row.version + 1 })
    return row
  }
  const api = mockApi({
    'GET /api/v1/projects/3/workspace': () => workspace(3, { acts, scenes }),
    'GET /api/v1/projects/3/storyline': { project_id: 3, version: 1, title: 'Lantern House' },
    'GET /api/v1/projects/3/characters': [character(9, 'Mira')],
    'GET /api/v1/projects/3/beats': () => beats,
    'POST /api/v1/projects/3/beats': call => { const row = beat(nextId++, '', null, 0, call.body as object) as Row; beats.push(row); return { status: 201, body: row } },
    ...Object.fromEntries([1, 2, 3, 50, 51].map(id => [`PATCH /api/v1/projects/3/beats/${id}`, patchBeat])),
    'POST /api/v1/projects/3/acts': call => { const row = { id: nextId++, screenplay_id: 12, title: (call.body as { title: string }).title, position: acts.length }; acts.push(row); return { status: 201, body: row } },
    'PATCH /api/v1/projects/3/acts/5': call => { Object.assign(acts[1], call.body); return acts[1] },
    'POST /api/v1/projects/3/scenes': call => { const row = { id: 70, act_id: (call.body as { act_id: number }).act_id, heading: (call.body as { heading: string }).heading, position: 0, body: '', version: 1, scene_instruction: '' }; scenes.push(row); return { status: 201, body: row } },
  })
  return { api, acts, beats, scenes }
}

describe('planBeatMove', () => {
  const beats = [beat(1, 'A', 4, 0), beat(2, 'B', 4, 1), beat(3, 'C', 5, 0), beat(4, 'D', null, 0)] as Beat[]
  const acts = new Set([4, 5])

  it('reorders within an act with the fewest patches', () => {
    expect(planBeatMove(beats, 2, 4, 0, acts).map(change => [change.beat.id, change.fields])).toEqual([[2, { position: 0 }], [1, { position: 1 }]])
  })

  it('moves between acts and closes the gap behind it', () => {
    expect(planBeatMove(beats, 1, 5, 1, acts).map(change => [change.beat.id, change.fields])).toEqual([[1, { act_id: 5, position: 1 }], [2, { position: 0 }]])
  })

  it('treats beats of unknown acts as unassigned', () => {
    const stray = [...beats, beat(5, 'E', 99, 0)] as Beat[]
    expect(planBeatMove(stray, 5, 4, 2, acts)[0].fields).toEqual({ act_id: 4, position: 2 })
  })
})

describe('OutlinePage', () => {
  it('shows any number of acts and adds beats and acts', async () => {
    const { api, acts } = outlineBackend()
    renderAt('/projects/3/outline')
    const actTwo = await screen.findByRole('region', { name: 'Act Two' })
    expect(within(screen.getByRole('region', { name: 'Act One' })).getAllByLabelText('Beat title')).toHaveLength(2)

    await userEvent.type(within(actTwo).getByLabelText('New beat in Act Two'), 'Fish story')
    await userEvent.click(within(actTwo).getByRole('button', { name: 'Add beat to Act Two' }))
    await waitFor(() => expect(within(actTwo).getAllByLabelText('Beat title')).toHaveLength(2))
    expect(api.calls.find(call => call.method === 'POST' && call.path.endsWith('/beats'))?.body).toEqual({ title: 'Fish story', act_id: 5, position: 1 })

    await userEvent.type(screen.getByLabelText('New act title'), 'Act Three')
    await userEvent.click(screen.getByRole('button', { name: 'Add act' }))
    expect(await screen.findByRole('region', { name: 'Act Three' })).toBeTruthy()
    expect(acts).toHaveLength(3)
  })

  it('moves beats with buttons, arrow keys and drag-and-drop', async () => {
    const { beats } = outlineBackend()
    renderAt('/projects/3/outline')
    const actOne = await screen.findByRole('region', { name: 'Act One' })
    await userEvent.click(within(within(actOne).getByRole('group', { name: 'Move The witch' })).getByRole('button', { name: 'Earlier' }))
    await waitFor(() => expect(within(actOne).getAllByLabelText<HTMLInputElement>('Beat title')[0].value).toBe('The witch'))

    within(actOne).getByRole('button', { name: 'Reorder Wedding toast' }).focus()
    await userEvent.keyboard('{ArrowRight}')
    await waitFor(() => expect(beats.find(row => row.id === 1)).toMatchObject({ act_id: 5, position: 1 }))

    const spectre = await screen.findByRole('article', { name: 'Beat Spectre' })
    fireEvent.dragStart(spectre, { dataTransfer: { setData: () => undefined, effectAllowed: 'move' } })
    fireEvent.drop(screen.getByRole('region', { name: 'Act One' }))
    await waitFor(() => expect(beats.find(row => row.id === 3)).toMatchObject({ act_id: 4, position: 1 }))
  })

  it('creates a scene from a beat and links it', async () => {
    const { api, beats } = outlineBackend()
    renderAt('/projects/3/outline')
    const card = await screen.findByRole('article', { name: 'Beat Spectre' })
    await userEvent.type(within(card).getByLabelText('Scene heading for Spectre'), 'EXT. SPECTRE - DAY')
    await userEvent.click(within(card).getByRole('button', { name: 'Create scene from beat' }))
    await waitFor(() => expect(beats.find(row => row.id === 3)?.scene_ids).toEqual([70]))
    expect(api.calls.find(call => call.path.endsWith('/scenes'))?.body).toMatchObject({ heading: 'EXT. SPECTRE - DAY', act_id: 5, screenplay_id: 12 })
    expect(await within(card).findByRole('link', { name: 'Open EXT. SPECTRE - DAY in the script' })).toBeTruthy()

    await userEvent.click(within(card).getByLabelText('Mira'))
    await waitFor(() => expect(beats.find(row => row.id === 3)?.character_ids).toEqual([9]))
  })

  it('renames an act and saves beat fields', async () => {
    const { acts, beats } = outlineBackend()
    renderAt('/projects/3/outline')
    const rename = await screen.findByLabelText('Rename Act Two')
    await userEvent.clear(rename)
    await userEvent.type(rename, 'The Road{Enter}')
    await waitFor(() => expect(acts[1].title).toBe('The Road'))

    const card = await screen.findByRole('article', { name: 'Beat Wedding toast' })
    await userEvent.type(within(card).getByLabelText('Summary of Wedding toast'), 'Edward steals the night.')
    await userEvent.selectOptions(within(card).getByLabelText('Type of Wedding toast'), 'inciting_incident')
    await waitFor(() => expect(beats[0]).toMatchObject({ summary: 'Edward steals the night.', beat_type: 'inciting_incident' }))
  })
})
