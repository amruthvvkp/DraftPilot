import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt, workspace } from './test/harness'

const developStory = {
  key: 'develop_story', label: 'Develop a story', description: 'From an idea to first scenes.', roles: ['story_architect'], proposes: true,
  params_schema: {
    type: 'object', required: ['idea'],
    properties: {
      idea: { type: 'string', title: 'Idea', maxLength: 20000 },
      stages: { type: 'array', title: 'Stages', items: { type: 'string', enum: ['storyline', 'characters', 'timelines', 'outline', 'scenes', 'coverage'] } },
      cast_size: { type: 'integer', title: 'Cast Size', default: 4, minimum: 1, maximum: 8 },
    },
  },
}

describe('Writers’ room launcher', () => {
  it('starts develop_story with idea, chosen stages and integers, and shows the current stage', async () => {
    const run = { id: 5, project_id: 3, kind: 'room_workflow', status: 'running', input: { workflow: 'develop_story' }, result: { trail: [{ step: 'storyline', role: 'story_architect', duration_ms: 1200, output: {} }] }, error: null, attempt_count: 1, max_attempts: 3 }
    const api = mockApi({
      'GET /api/v1/projects/3/workspace': workspace(3),
      'GET /api/v1/projects/3/room/workflows': [developStory],
      'GET /api/v1/projects/3/runs': [run],
      'GET /api/v1/projects/3/agent-proposals': [{ id: 1, project_id: 3, run_id: 5, target_kind: 'storyline', target_id: 3, operation: {}, diff: { summary: 'Storyline' }, before: {}, base_version: 1, status: 'proposed' }],
      'POST /api/v1/projects/3/room/workflows': { status: 202, body: { ...run, id: 6 } },
    })
    renderAt('/projects/3/room')
    const launcher = await screen.findByRole('region', { name: 'Room workflows' })
    const stages = await within(launcher).findByRole('group', { name: 'Stages' })
    expect(within(stages).getAllByRole('checkbox').every(box => (box as HTMLInputElement).checked)).toBe(true)
    await userEvent.click(within(stages).getByRole('checkbox', { name: 'coverage' }))
    await userEvent.click(within(stages).getByRole('checkbox', { name: 'scenes' }))
    await userEvent.type(within(launcher).getByLabelText('Idea'), 'A son pieces together his father’s tall tales.')
    const cast = within(launcher).getByLabelText('Cast Size')
    await userEvent.clear(cast)
    await userEvent.type(cast, '5')
    await userEvent.click(within(launcher).getByRole('button', { name: 'Start develop a story' }))
    await waitFor(() => expect(api.calls.some(call => call.method === 'POST')).toBe(true))
    expect(api.calls.find(call => call.method === 'POST')?.body).toEqual({
      workflow: 'develop_story', provider_profile_id: null,
      params: { idea: 'A son pieces together his father’s tall tales.', stages: ['storyline', 'characters', 'timelines', 'outline'], cast_size: 5 },
    })
    expect(await screen.findByText('Waiting for your decisions · storyline')).toBeTruthy()
  })
})
