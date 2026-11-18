import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { projectStages } from '../project/progress'
import type { ProjectWorkspace } from '../api'
import { beat, character, mockApi, renderAt, workspace } from '../test/harness'

type Scene = { id: number; act_id: number; heading: string; position: number; body: string; version: number; scene_instruction: string }
const scene = (id: number, heading: string, actId: number, position: number): Scene => ({ id, act_id: actId, heading, position, body: '', version: 1, scene_instruction: '' })
const block = (id: number, sceneId: number, elementType: string, text: string) => ({ id, scene_id: sceneId, position: 0, element_type: elementType, text, character_extension: null, is_dual: false, dual_group: null, translation: null, translation_lang: null })

function scriptBackend(initial: Scene[]) {
  const scenes = [...initial]
  const blocks: Record<number, ReturnType<typeof block>[]> = { 7: [block(20, 7, 'action', 'The house breathes.')] }
  const acts = [{ id: 4, screenplay_id: 12, title: 'Act One', position: 0 }, { id: 5, screenplay_id: 12, title: 'Act Two', position: 1 }]
  const api = mockApi({
    'GET /api/v1/projects/3/workspace': () => workspace(3, { acts, scenes, blocks }),
    'GET /api/v1/projects/3/storyline': { project_id: 3, version: 1, title: 'Lantern House' },
    'GET /api/v1/projects/3/characters': [],
    'GET /api/v1/projects/3/beats': [],
    'POST /api/v1/projects/3/scenes': call => { const row = scene(30, (call.body as { heading: string }).heading, 4, scenes.length); scenes.push(row); return { status: 201, body: row } },
    'POST /api/v1/projects/3/scenes/7/move': call => { Object.assign(scenes[0], { act_id: (call.body as { act_id: number }).act_id, position: 0, version: 2 }); return scenes[0] },
    'DELETE /api/v1/projects/3/scenes/7': () => { scenes.splice(0, 1); return { status: 204 } },
    'PATCH /api/v1/projects/3/scenes/7/blocks/20': call => { Object.assign(blocks[7][0], call.body); return blocks[7][0] },
    'PUT /api/v1/projects/3/scenes/7/content': call => {
      const sent = (call.body as { blocks: (Partial<ReturnType<typeof block>> & { id: number })[] }).blocks
      blocks[7] = sent.map(item => ({ ...blocks[7].find(row => row.id === item.id)!, ...item }))
      scenes[0].version += 1
      return { scene_id: 7, version: scenes[0].version, block_ids: sent.map(item => item.id), created_ids: [] }
    },
  })
  return { api, scenes, blocks }
}

describe('Script workspace', () => {
  it('creates the first scene of an empty project', async () => {
    const { api } = scriptBackend([])
    renderAt('/projects/3')
    expect(await screen.findByText('Your first scene starts here.')).toBeTruthy()
    const heading = screen.getByLabelText('New scene heading')
    await userEvent.clear(heading)
    await userEvent.type(heading, 'INT. ATTIC - NIGHT')
    await userEvent.click(screen.getByRole('button', { name: '＋ Create the first scene' }))
    expect(await screen.findByDisplayValue('INT. ATTIC - NIGHT')).toBeTruthy()
    expect(api.calls.find(call => call.method === 'POST')?.body).toEqual({ heading: 'INT. ATTIC - NIGHT', act_id: null, position: null, screenplay_id: 12 })
  })

  it('changes a block type directly, moves and deletes scenes', async () => {
    const { api, scenes } = scriptBackend([scene(7, 'INT. HALL - NIGHT', 4, 0)])
    renderAt('/projects/3')
    await userEvent.selectOptions(await screen.findByLabelText('Format action'), 'transition')
    await waitFor(() => expect(api.calls.some(call => call.method === 'PATCH' && (call.body as { element_type?: string }).element_type === 'transition')).toBe(true))
    expect(api.calls.some(call => call.path.endsWith('/agent-proposals') && call.method === 'POST')).toBe(false)

    const actions = screen.getByRole('group', { name: 'Selected scene actions' })
    await userEvent.click(within(actions).getByRole('button', { name: 'Move scene down' }))
    await waitFor(() => expect(scenes[0].act_id).toBe(5))
    expect(api.calls.find(call => call.path.endsWith('/move'))?.headers.get('If-Match')).toBe('1')

    await userEvent.click(within(screen.getByRole('group', { name: 'Selected scene actions' })).getByRole('button', { name: 'Delete scene' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete scene' }))
    expect(await screen.findByText('Your first scene starts here.')).toBeTruthy()
  })

  it('keeps focus where the writer moved it right after a formatting click', async () => {
    const { blocks } = scriptBackend([scene(7, 'INT. HALL - NIGHT', 4, 0)])
    blocks[7].push(block(21, 7, 'dialogue', 'We should go.'))
    const user = userEvent.setup({ delay: null })
    renderAt('/projects/3')
    const action = await screen.findByLabelText('Edit action') as HTMLTextAreaElement
    await user.click(action)
    action.setSelectionRange(4, 9)
    fireEvent.click(screen.getByRole('button', { name: 'Bold text' }))
    // The writer tabs on before the editor's deferred work runs.
    const dialogue = screen.getByLabelText('Edit dialogue') as HTMLTextAreaElement
    dialogue.focus()
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(document.activeElement).toBe(dialogue)
    expect(action.value).toBe('The **house** breathes.')
  })

  it('pairs a dialogue with the previous speech and unpairs it in one content write', async () => {
    const { api, blocks } = scriptBackend([scene(7, 'INT. HALL - NIGHT', 4, 0)])
    blocks[7].push(block(21, 7, 'character', 'MIRA'), block(22, 7, 'dialogue', 'We should go.'), block(23, 7, 'character', 'EDWARD'), block(24, 7, 'dialogue', 'Not yet.'))
    renderAt('/projects/3')
    // The first speech has nothing before it to pair with.
    expect((await screen.findByRole('button', { name: 'Pair with previous dialogue (block 3)' })).hasAttribute('disabled')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Pair with previous dialogue (block 5)' }))
    await waitFor(() => expect(blocks[7].slice(1).every(row => row.is_dual && row.dual_group === 1)).toBe(true))
    const write = api.calls.find(call => call.method === 'PUT')!
    expect(write.headers.get('If-Match')).toBe('1')
    expect((write.body as { blocks: { id: number; is_dual: boolean }[] }).blocks.map(row => [row.id, row.is_dual])).toEqual([[20, false], [21, true], [22, true], [23, true], [24, true]])
    expect(document.querySelector('.semantic-blocks.has-dual')).not.toBeNull()
    expect(document.querySelectorAll('.semantic-row.dual-left')).toHaveLength(2)
    expect(document.querySelectorAll('.semantic-row.dual-right')).toHaveLength(2)

    await userEvent.click(await screen.findByRole('button', { name: 'Unpair dual dialogue (block 3)' }))
    await waitFor(() => expect(blocks[7].every(row => !row.is_dual && row.dual_group === null)).toBe(true))
    await waitFor(() => expect(document.querySelector('.has-dual')).toBeNull())
  })

  it('toggles the continuous view for real', async () => {
    scriptBackend([scene(7, 'INT. HALL - NIGHT', 4, 0)])
    renderAt('/projects/3')
    const toggle = await screen.findByRole('switch', { name: /Continuous view/ })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.editorView).toBe('paginated')
    expect(screen.getByRole('switch', { name: /Continuous view/ }).getAttribute('aria-checked')).toBe('false')
  })
})

describe('projectStages', () => {
  it('summarises progress and lists gaps with links', () => {
    const ws = workspace(3, { scenes: [scene(7, 'INT. HALL - NIGHT', 4, 0)], blocks: {} }) as unknown as ProjectWorkspace
    const stages = projectStages({
      projectId: 3,
      storyline: { project_id: 3, version: 1, title: 'T', logline: 'L', premise: null, synopsis: null, theme: null, tone: null, description: null, story_outline: null },
      characters: [character(1, 'Mira', { motive: 'x', objective: 'y' }), character(2, 'Tom')] as never,
      beats: [beat(1, 'Toast', 4, 0, { scene_ids: [7] })] as never,
      workspace: ws,
    })
    expect(stages.map(stage => [stage.key, stage.state, stage.summary])).toEqual([
      ['storyline', 'started', 'Logline set · 1/5'],
      ['characters', 'started', '2 · 1 with motive & objective'],
      ['outline', 'done', '1 beats · 1 linked'],
      ['script', 'started', '1 scenes'],
    ])
    expect(stages[0].gaps[0]).toEqual({ label: 'Premise is empty', to: '/projects/3/storyline?field=premise' })
    expect(stages[1].gaps.map(gap => gap.to)).toEqual(['/projects/3/characters/1?field=want', '/projects/3/characters/2?field=motive'])
    expect(stages[3].gaps).toEqual([{ label: 'INT. HALL - NIGHT is empty', to: '/projects/3?scene=7' }])
  })
})
