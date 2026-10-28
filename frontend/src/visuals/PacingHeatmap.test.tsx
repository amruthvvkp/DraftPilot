import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt } from '../test/harness'
import { sampleVisuals, visualsRoutes } from './fixtures'

describe('PacingHeatmap', () => {
  it('shows one row per act with scenes sized by runtime and coloured by intensity', async () => {
    mockApi(visualsRoutes(sampleVisuals()))
    renderAt('/projects/3/visuals/pacing')
    const actOne = await screen.findByRole('listitem', { name: 'Act One' })
    const cells = within(actOne).getAllByRole('img')
    expect(cells.map(cell => cell.getAttribute('aria-label'))).toEqual(['EXT. RIVER - DAY: 1:00, intensity +1', 'INT. CIRCUS - NIGHT: 2:00, intensity +4'])
    expect(Number((cells[1] as HTMLElement).style.flexGrow)).toBeCloseTo(2 / 3)
    expect(within(screen.getByRole('listitem', { name: 'Act Two' })).getAllByRole('img')[0].getAttribute('aria-label')).toContain('intensity —')
    const table = within(screen.getByRole('table'))
    expect(table.getByRole('row', { name: /Act One/ }).textContent).toContain('60%')
    expect(table.getByRole('row', { name: /Act Two/ }).textContent).toContain('-3')
  })
})
