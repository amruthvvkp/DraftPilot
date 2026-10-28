import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi, renderAt } from '../test/harness'
import { sampleVisuals, visualsRoutes } from './fixtures'

describe('RelationshipGraph', () => {
  it('ranks links by shared moments and focuses a character', async () => {
    mockApi(visualsRoutes(sampleVisuals()))
    renderAt('/projects/3/visuals/relationships')
    const graph = await screen.findByRole('img', { name: 'Relationship graph of 3 characters and 3 links' })
    expect(graph.querySelectorAll('line.graph-edge')).toHaveLength(3)
    expect(graph.querySelectorAll('line.graph-edge.weak')).toHaveLength(1)
    const links = () => within(screen.getByRole('list', { name: 'Links' })).getAllByRole('listitem').map(item => item.textContent)
    expect(links()[0]).toBe('Edward – Sandra2 shared moments · 1 shared scene')
    expect(links()[1]).toContain('son')

    await userEvent.click(within(screen.getByRole('group', { name: 'Focus a character' })).getByRole('button', { name: 'Will' }))
    expect(screen.getByRole('heading', { name: 'Links of Will' })).toBeTruthy()
    expect(links()).toHaveLength(2)
    expect(graph.querySelectorAll('line.graph-edge.off')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Will' }))
    expect(screen.getByRole('heading', { name: 'Strongest links' })).toBeTruthy()
  })

  it('points to the Characters page with no cast', async () => {
    mockApi(visualsRoutes(sampleVisuals({ characters: [], edges: [] })))
    renderAt('/projects/3/visuals/relationships')
    expect((await screen.findByRole('link', { name: 'Characters' })).getAttribute('href')).toBe('/projects/3/characters')
  })
})
