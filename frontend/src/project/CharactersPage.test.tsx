import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { type Call, character, mockApi, renderAt, workspace } from '../test/harness'

type Row = Record<string, unknown> & { id: number; version: number }

/** A fake character/timeline/relationship backend with versioned rows. */
function storyBackend() {
  const cast: Row[] = [character(1, 'Mira', { role: 'protagonist', motive: 'Guilt', objective: 'Sell the house', version: 2 }), character(2, 'Old Tom', { source: 'twin', dialogue_lines: 12, scene_ids: [7] })]
  const events: Row[] = []
  const relationships: Row[] = []
  let nextId = 100
  const patch = (rows: Row[], call: Call) => {
    const id = Number(call.path.split('/').pop())
    const row = rows.find(item => item.id === id)!
    if (call.headers.get('If-Match') !== String(row.version)) return { status: 409, body: { detail: 'Row has changed' } }
    Object.assign(row, call.body, { version: row.version + 1 })
    return row
  }
  const remove = (rows: Row[], call: Call) => {
    const id = Number(call.path.split('/').pop())
    rows.splice(rows.findIndex(item => item.id === id), 1)
    return { status: 204 }
  }
  const api = mockApi({
    'GET /api/v1/projects/3/workspace': workspace(3, { scenes: [{ id: 7, act_id: 4, heading: 'INT. HALL - NIGHT', position: 0, body: '', version: 1, scene_instruction: '' }] }),
    'GET /api/v1/projects/3/storyline': { project_id: 3, version: 1, title: 'Lantern House' },
    'GET /api/v1/projects/3/beats': [],
    'GET /api/v1/projects/3/characters': () => cast,
    'POST /api/v1/projects/3/characters': call => { const row = character(nextId++, '', call.body as object) as Row; cast.push(row); return { status: 201, body: row } },
    'PATCH /api/v1/projects/3/characters/1': call => patch(cast, call),
    'DELETE /api/v1/projects/3/characters/2': call => remove(cast, call),
    'GET /api/v1/projects/3/relationships': () => relationships,
    'POST /api/v1/projects/3/relationships': call => { const row = { id: nextId++, project_id: 3, version: 1, ...(call.body as object) }; relationships.push(row); return { status: 201, body: row } },
    'GET /api/v1/projects/3/timeline-events?character_id=1': () => events.filter(row => row.character_id === 1),
    'POST /api/v1/projects/3/timeline-events': call => { const row = { id: nextId++, project_id: 3, version: 1, description: '', objective: '', emotional_state: '', story_time: '', scene_id: null, beat_id: null, ...(call.body as object) } as Row; events.push(row); return { status: 201, body: row } },
    ...Object.fromEntries([100, 101, 102, 103, 104].map(id => [`PATCH /api/v1/projects/3/timeline-events/${id}`, (call: Call) => patch(events, call)])),
    ...Object.fromEntries([100, 101, 102, 103, 104].map(id => [`DELETE /api/v1/projects/3/timeline-events/${id}`, (call: Call) => remove(events, call)])),
  })
  return { api, cast, events, relationships }
}

describe('CharactersPage', () => {
  it('lists the cast with role and source, and creates a character', async () => {
    const { api } = storyBackend()
    renderAt('/projects/3/characters')
    const cast = await screen.findByRole('region', { name: 'Cast' })
    const mira = await within(cast).findByRole('link', { name: /Mira/ })
    expect(mira.textContent).toContain('protagonist')
    expect(mira.textContent).toContain('Motive & objective set')
    expect(within(cast).getByRole('link', { name: /Old Tom/ }).textContent).toContain('from draft')

    await userEvent.type(screen.getByLabelText('New character name'), 'Will')
    await userEvent.type(screen.getByLabelText('New character role'), 'mentor')
    await userEvent.click(screen.getByRole('button', { name: 'Add character' }))
    expect(await screen.findByRole('region', { name: 'Character Will' })).toBeTruthy()
    expect(api.calls.find(call => call.method === 'POST')?.body).toEqual({ name: 'Will', role: 'mentor', position: 2 })
  })

  it('saves profile fields with the row version', async () => {
    const { api } = storyBackend()
    renderAt('/projects/3/characters/1')
    const want = await screen.findByLabelText('Want')
    await userEvent.type(want, 'To be forgiven')
    await userEvent.type(screen.getByLabelText('Aliases'), 'Mi, The Heir')
    await userEvent.click(screen.getByRole('button', { name: 'Save profile' }))
    expect(await screen.findByText('Profile saved.')).toBeTruthy()
    const patch = api.calls.find(call => call.method === 'PATCH')!
    expect(patch.headers.get('If-Match')).toBe('2')
    expect(patch.body).toEqual({ want: 'To be forgiven', aliases: ['Mi', 'The Heir'] })
  })

  it('adds a relationship to another character', async () => {
    const { relationships } = storyBackend()
    renderAt('/projects/3/characters/1')
    const section = await screen.findByRole('region', { name: 'Relationships' })
    await userEvent.selectOptions(within(section).getByLabelText('Related character'), '2')
    await userEvent.type(within(section).getByLabelText('Relation'), 'granddaughter of')
    await userEvent.click(within(section).getByRole('button', { name: 'Add relationship' }))
    await waitFor(() => expect(relationships).toHaveLength(1))
    expect(relationships[0]).toMatchObject({ source_character_id: 1, target_character_id: 2, relation: 'granddaughter of' })
    expect(await within(section).findByLabelText('Relation between Mira and Old Tom')).toBeTruthy()
  })

  it('edits a per-character timeline: add, link a scene, reorder and delete', async () => {
    const { api, events } = storyBackend()
    renderAt('/projects/3/characters/1')
    const timeline = await screen.findByRole('region', { name: 'Mira timeline' })
    const form = within(timeline).getByRole('form', { name: 'New timeline event' })
    for (const [title, time] of [['Arrives at the house', 'Day 1'], ['Finds the ledger', 'Day 2']]) {
      await userEvent.type(within(form).getByLabelText('Event'), title)
      await userEvent.type(within(form).getByLabelText('Story time'), time)
      if (time === 'Day 2') await userEvent.selectOptions(within(form).getByLabelText('Scene'), '7')
      await userEvent.click(within(form).getByRole('button', { name: 'Add event' }))
      await within(timeline).findByText(title)
    }
    expect(events.map(row => [row.title, row.position, row.character_id, row.scene_id])).toEqual([['Arrives at the house', 0, 1, null], ['Finds the ledger', 1, 1, 7]])
    expect(within(timeline).getByText('Scene: INT. HALL - NIGHT')).toBeTruthy()

    await userEvent.click(within(timeline).getByRole('button', { name: 'Move Finds the ledger earlier' }))
    await waitFor(() => expect(Object.fromEntries(events.map(row => [row.title, row.position]))).toEqual({ 'Arrives at the house': 1, 'Finds the ledger': 0 }))
    const items = await within(timeline).findAllByRole('listitem')
    await waitFor(() => expect(items[0].textContent).toContain('Finds the ledger'))
    const moves = api.calls.filter(call => call.method === 'PATCH' && call.path.includes('timeline-events'))
    expect(moves.every(call => call.headers.get('If-Match') === '1')).toBe(true)

    await userEvent.click(within(timeline).getByRole('button', { name: 'Delete Arrives at the house' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete event' }))
    await waitFor(() => expect(events).toHaveLength(1))
    await waitFor(() => expect(within(timeline).queryByText('Arrives at the house')).toBeNull())
  })

  it('deletes a character only after confirmation', async () => {
    const { cast } = storyBackend()
    renderAt('/projects/3/characters/2')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete character' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete Old Tom?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(cast).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Delete character' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete character' }))
    await waitFor(() => expect(cast).toHaveLength(1))
    expect(await screen.findByText('Choose a character to edit their profile and timeline.')).toBeTruthy()
  })
})
