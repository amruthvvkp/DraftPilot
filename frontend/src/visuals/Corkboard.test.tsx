import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Beat } from '../storyApi'
import { beat, type Call, mockApi, renderAt } from '../test/harness'
import { sampleVisuals, visualsRoutes } from './fixtures'

type Row = Beat & Record<string, unknown>

function board() {
  const beats = [beat(1, 'Wedding toast', 4, 0, { beat_type: 'inciting_incident', summary: 'Edward steals the night.' }), beat(2, 'The witch', 4, 1), beat(3, 'Spectre', 5, 0)] as Row[]
  const patches: [number, string | null, unknown][] = []
  const patch = (call: Call) => {
    const row = beats.find(item => item.id === Number(call.path.split('/').pop()))!
    patches.push([row.id, call.headers.get('If-Match'), call.body])
    if (call.headers.get('If-Match') !== String(row.version)) return { status: 409, body: { detail: 'Beat has changed' } }
    Object.assign(row, call.body, { version: row.version + 1 })
    return row
  }
  const api = mockApi({ ...visualsRoutes(sampleVisuals(), beats), ...Object.fromEntries([1, 2, 3].map(id => [`PATCH /api/v1/projects/3/beats/${id}`, patch])) })
  return { api, beats, patches }
}

const titles = (name: string) => within(screen.getByRole('region', { name })).queryAllByRole('heading', { level: 3 }).map(item => item.textContent)

describe('Corkboard', () => {
  it('shows beats as index cards per act', async () => {
    board()
    renderAt('/projects/3/visuals/corkboard')
    await screen.findByRole('article', { name: 'Wedding toast, card 1 of 2 in Act One' })
    expect(titles('Act One')).toEqual(['Wedding toast', 'The witch'])
    expect(titles('Act Two')).toEqual(['Spectre'])
    expect(screen.getByText('Edward steals the night.')).toBeTruthy()
    expect(screen.getByText('inciting incident')).toBeTruthy()
  })

  it('reorders with the arrow keys through versioned beat PATCHes and keeps focus on the card', async () => {
    const { patches } = board()
    renderAt('/projects/3/visuals/corkboard')
    const witch = await screen.findByRole('article', { name: /^The witch/ })
    witch.focus()
    fireEvent.keyDown(witch, { key: 'ArrowUp' })
    await waitFor(() => expect(titles('Act One')).toEqual(['The witch', 'Wedding toast']))
    await waitFor(() => expect(patches).toEqual([[2, '1', { position: 0 }], [1, '1', { position: 1 }]]))
    expect(document.activeElement?.getAttribute('aria-label')).toMatch(/^The witch, card 1 of 2/)
    expect(screen.getByRole('status').textContent).toBe('Moved The witch to position 1 in Act One')

    fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' })
    await waitFor(() => expect(titles('Act Two')).toEqual(['Spectre', 'The witch']))
    await waitFor(() => expect(patches.at(-2)).toEqual([2, '2', { act_id: 5, position: 1 }]))
    expect(patches.at(-1)).toEqual([1, '2', { position: 0 }])
    expect(document.activeElement?.getAttribute('aria-label')).toMatch(/^The witch, card 2 of 2 in Act Two/)
  })

  it('moves with the card buttons and ignores moves past the edge', async () => {
    const { patches } = board()
    renderAt('/projects/3/visuals/corkboard')
    const spectre = await screen.findByRole('group', { name: 'Move Spectre' })
    expect((within(spectre).getByRole('button', { name: 'Next act' }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.click(within(spectre).getByRole('button', { name: 'Previous act' }))
    await waitFor(() => expect(titles('Act One')).toEqual(['Wedding toast', 'The witch', 'Spectre']))
    await waitFor(() => expect(patches).toEqual([[3, '1', { act_id: 4, position: 2 }]]))
    fireEvent.keyDown(screen.getByRole('article', { name: /^Wedding toast/ }), { key: 'ArrowUp' })
    expect(patches).toHaveLength(1)
  })

  it('reports a failed save and reloads the beats', async () => {
    const beats = [beat(1, 'A', 4, 0), beat(2, 'B', 4, 1)]
    const api = mockApi({ ...visualsRoutes(sampleVisuals(), beats), 'PATCH /api/v1/projects/3/beats/2': { status: 409, body: { detail: 'Beat has changed' } } })
    renderAt('/projects/3/visuals/corkboard')
    fireEvent.keyDown(await screen.findByRole('article', { name: /^B,/ }), { key: 'ArrowUp' })
    expect((await screen.findByRole('alert')).textContent).toContain('Someone else changed this')
    await waitFor(() => expect(titles('Act One')).toEqual(['A', 'B']))
    expect(api.calls.filter(call => call.path === '/api/v1/projects/3/beats').length).toBeGreaterThan(1)
  })
})
