import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt } from '../test/harness'
import { sampleVisuals, visualsRoutes } from './fixtures'

describe('TensionCurve', () => {
  it('draws the cast average per scene, act breaks and milestones', async () => {
    const api = mockApi(visualsRoutes(sampleVisuals()))
    const { container } = renderAt('/projects/3/visuals')
    const chart = await screen.findByRole('img', { name: 'Tension curve across 4 scenes, 3 with intensity, 1 milestones' })
    expect(chart.querySelectorAll('path.chart-line')).toHaveLength(2)
    expect(chart.querySelectorAll('circle.chart-point')).toHaveLength(3)
    expect(within(chart).getByText('Meets Sandra')).toBeTruthy()
    expect(within(chart).getByText('Act Two')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Tension curve' }).className).toContain('active')
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows[2].textContent).toContain('+4')
    expect(rows[2].textContent).toContain('Meets Sandra')
    expect(screen.getByText(/Not linked to a scene yet: The end \(climax\)/)).toBeTruthy()
    expect(container.querySelector('nav[aria-label="Studio tools"] a[href="/projects/3/visuals"]')).toBeTruthy()
    expect(api.calls.some(call => call.path === '/api/v1/projects/3/visuals')).toBe(true)
  })

  it('explains what to do with no scenes or no ratings', async () => {
    mockApi(visualsRoutes(sampleVisuals({ scenes: [] })))
    renderAt('/projects/3/visuals/tension')
    expect(await screen.findByText(/No scenes yet/)).toBeTruthy()
  })

  it('asks for intensities when no scene is rated, and passes the chosen draft', async () => {
    const visuals = sampleVisuals()
    const api = mockApi({ ...visualsRoutes({ ...visuals, scenes: visuals.scenes.map(item => ({ ...item, intensity: null })) }), 'GET /api/v1/projects/3/workspace?screenplay_id=12': {} })
    renderAt('/projects/3/visuals/tension?draft=12')
    expect(await screen.findByText(/No scene has rated events yet/)).toBeTruthy()
    expect(api.calls.some(call => call.path === '/api/v1/projects/3/visuals?screenplay_id=12')).toBe(true)
  })
})
