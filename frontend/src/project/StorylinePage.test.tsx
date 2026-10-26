import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt, workspace } from '../test/harness'

const base = { 'GET /api/v1/projects/3/workspace': workspace(3), 'GET /api/v1/projects/3/characters': [], 'GET /api/v1/projects/3/beats': [] }
const storyline = (version: number, extra: Record<string, unknown> = {}) => ({
  project_id: 3, version, title: 'Lantern House', logline: 'A house remembers.', premise: null, synopsis: null, theme: null, tone: null, description: null, story_outline: null, ...extra,
})

describe('StorylinePage', () => {
  it('edits every storyline field and saves only the changes with If-Match', async () => {
    let current = storyline(4)
    const api = mockApi({
      ...base,
      'GET /api/v1/projects/3/storyline': () => current,
      'PATCH /api/v1/projects/3': call => { current = { ...current, ...(call.body as object), version: 5 }; return { id: 3, ...current } },
    })
    renderAt('/projects/3/storyline')
    const logline = await screen.findByLabelText('Logline')
    expect((logline as HTMLTextAreaElement).value).toBe('A house remembers.')
    for (const label of ['Title', 'Premise', 'Synopsis', 'Theme', 'Tone', 'Description', 'Story notes']) expect(screen.getByLabelText(label)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Saved' }) as HTMLButtonElement).disabled).toBe(true)

    await userEvent.type(screen.getByLabelText('Premise'), 'What if a house kept score?')
    await userEvent.type(screen.getByLabelText('Theme'), 'Memory')
    await userEvent.click(screen.getByRole('button', { name: 'Save storyline' }))

    expect(await screen.findByText('Storyline saved.')).toBeTruthy()
    const patch = api.calls.find(call => call.method === 'PATCH')!
    expect(patch.headers.get('If-Match')).toBe('4')
    expect(patch.body).toEqual({ premise: 'What if a house kept score?', theme: 'Memory' })
    expect(screen.getByText(/Version 5/)).toBeTruthy()
  })

  it('keeps the writer’s edits on a 409 and saves again over the latest version', async () => {
    let version = 1
    const patches: string[] = []
    mockApi({
      ...base,
      'GET /api/v1/projects/3/storyline': () => storyline(version, { tone: version > 1 ? 'Wry' : null }),
      'PATCH /api/v1/projects/3': call => {
        patches.push(call.headers.get('If-Match') ?? '')
        if (patches.length === 1) { version = 2; return { status: 409, body: { detail: 'Project has changed' } } }
        return { id: 3, version: 3 }
      },
    })
    renderAt('/projects/3/storyline')
    const logline = await screen.findByLabelText('Logline')
    await userEvent.clear(logline)
    await userEvent.type(logline, 'Mine.')
    await userEvent.click(screen.getByRole('button', { name: 'Save storyline' }))

    expect(await screen.findByText(/changed in another session/)).toBeTruthy()
    await waitFor(() => expect((screen.getByLabelText('Tone') as HTMLTextAreaElement).value).toBe('Wry'))
    expect((screen.getByLabelText('Logline') as HTMLTextAreaElement).value).toBe('Mine.')
    await userEvent.click(screen.getByRole('button', { name: 'Save my version' }))
    expect(await screen.findByText('Storyline saved.')).toBeTruthy()
    expect(patches).toEqual(['1', '2'])
  })

  it('focuses the field a Context map link names', async () => {
    mockApi({ ...base, 'GET /api/v1/projects/3/storyline': storyline(1) })
    renderAt('/projects/3/storyline?field=synopsis')
    const synopsis = await screen.findByLabelText('Synopsis')
    await waitFor(() => expect(document.activeElement).toBe(synopsis))
  })
})
