import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Beat } from '../storyApi'
import { beat, type Call, mockApi, renderAt } from '../test/harness'
import { sampleVisuals, visualsRoutes } from './fixtures'
import { actFor, matchTemplate, planTemplateBeats, TEMPLATES } from './templates'

const [saveTheCat, herosJourney, fiveActs] = TEMPLATES

describe('structure templates', () => {
  it('are static, ordered and within the runtime', () => {
    expect(TEMPLATES.map(item => [item.name, item.beats.length])).toEqual([['Save the Cat', 15], ['Hero’s Journey', 12], ['Five acts', 7]])
    for (const template of TEMPLATES) {
      expect(template.beats.map(item => item.at)).toEqual([...template.beats.map(item => item.at)].sort((a, b) => a - b))
      expect(template.beats.every(item => item.at >= 0 && item.at <= 1 && item.act < template.acts.length)).toBe(true)
    }
  })

  it('matches by title first, then by a structural type, each beat once', () => {
    const beats = [beat(1, 'catalyst ', 4, 0, { beat_type: 'beat' }), beat(2, 'Big turn', 5, 0, { beat_type: 'midpoint' }), beat(3, 'Low', 5, 1, { beat_type: 'crisis' })] as Beat[]
    const matches = matchTemplate(saveTheCat, beats)
    const found = Object.fromEntries(matches.filter(item => item.beat).map(item => [item.target.title, item.beat!.id]))
    expect(found).toEqual({ Catalyst: 1, Midpoint: 2, 'All Is Lost': 3 })
  })

  it('plans the missing beats into the matching acts, after the existing ones', () => {
    expect([actFor(4, [10, 11, 12]), actFor(1, [10, 11, 12]), actFor(0, [])]).toEqual([12, 11, null])
    const beats = [beat(1, 'Exposition', 10, 0), beat(2, 'Something', 11, 3)] as Beat[]
    const plan = planTemplateBeats(matchTemplate(fiveActs, beats), beats, [10, 11, 12])
    expect(plan.map(item => [item.title, item.act_id, item.position])).toEqual([
      ['Inciting moment', 10, 1], ['Rising action', 11, 4], ['Climax', 12, 0], ['Falling action', 12, 1], ['Final suspense', 12, 2], ['Dénouement', 12, 3],
    ])
    expect(plan[0]).toMatchObject({ beat_type: 'inciting_incident', status: 'planned' })
  })
})

describe('StructureTemplatesPage', () => {
  it('overlays a template on the outline and adds missing beats only after the writer confirms', async () => {
    const beats = [beat(1, 'Call to Adventure', 4, 0, { scene_ids: [22] }), beat(2, 'Ordeal', 5, 0, { beat_type: 'midpoint' })]
    const created: unknown[] = []
    const api = mockApi({
      ...visualsRoutes(sampleVisuals(), beats),
      'POST /api/v1/projects/3/beats': (call: Call) => { created.push(call.body); return { status: 201, body: beat(50 + created.length, 'x', null, 0) } },
    })
    renderAt('/projects/3/visuals/structure')
    await userEvent.click(await screen.findByRole('radio', { name: 'Hero’s Journey' }))
    const overlay = await screen.findByRole('region', { name: 'Hero’s Journey overlay' })
    expect(within(overlay).getByRole('img').getAttribute('aria-label')).toBe('Hero’s Journey: 12 target beats, 2 matched')
    const row = within(overlay).getByRole('row', { name: /Call to Adventure/ })
    expect(row.textContent).toContain('20%')
    expect(within(overlay).getByRole('row', { name: /Reward/ }).textContent).toContain('Missing')

    await userEvent.click(within(overlay).getByRole('button', { name: 'Add 10 missing beats to the outline' }))
    const dialog = screen.getByRole('dialog', { name: 'Add 10 Hero’s Journey beats?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(api.calls.some(call => call.method === 'POST')).toBe(false)

    await userEvent.click(within(overlay).getByRole('button', { name: 'Add 10 missing beats to the outline' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Add beats' }))
    await waitFor(() => expect(created).toHaveLength(10))
    expect(created[0]).toEqual({ title: 'Ordinary World', summary: 'The hero at home, before the adventure.', beat_type: 'opening_image', act_id: 4, position: 1, status: 'planned' })
    expect(await screen.findByText('Added 10 target beats to the outline.')).toBeTruthy()
    expect(herosJourney.beats).toHaveLength(12)
  })
})
