import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { subscribeProjectEvents } from './api'
import { invalidateForEvent, keys, staleKeysFor } from './data/queries'
import { FakeEventSource, mockApi, project, renderAt, workspace } from './test/harness'

const storyline = (version: number, logline: string) => ({ project_id: 3, version, title: 'Lantern House', logline, premise: null, synopsis: null, theme: null, tone: null, description: null, story_outline: null })

describe('routing', () => {
  it('opens a project from the library without a page reload', async () => {
    mockApi({
      'GET /api/v1/projects': [project(3)],
      'GET /api/v1/projects/deleted': [],
      'GET /api/v1/projects/3/workspace': workspace(3),
      'GET /api/v1/projects/3/storyline': storyline(1, ''),
      'GET /api/v1/projects/3/characters': [],
      'GET /api/v1/projects/3/beats': [],
    })
    const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => undefined)
    renderAt('/projects')
    await userEvent.click(await screen.findByRole('heading', { name: 'Lantern House' }))
    expect(await screen.findByText('Your first scene starts here.')).toBeTruthy()
    expect(assign).not.toHaveBeenCalled()
    expect(screen.getByRole('navigation', { name: 'Project steps' })).toBeTruthy()
  })

  it('keeps the legacy beat-board URL working as the Outline', async () => {
    mockApi({ 'GET /api/v1/projects/3/workspace': workspace(3), 'GET /api/v1/projects/3/beats': [], 'GET /api/v1/projects/3/characters': [] })
    renderAt('/projects/3/beats')
    expect(await screen.findByRole('heading', { name: 'Outline' })).toBeTruthy()
    expect(await screen.findByRole('region', { name: 'Act One' })).toBeTruthy()
  })

  it('shows stage completion in the stepper', async () => {
    mockApi({
      'GET /api/v1/projects/3/workspace': workspace(3),
      'GET /api/v1/projects/3/storyline': storyline(1, 'A house remembers.'),
      'GET /api/v1/projects/3/characters': [],
      'GET /api/v1/projects/3/beats': [],
    })
    renderAt('/projects/3/storyline')
    const steps = screen.getByRole('navigation', { name: 'Project steps' })
    await waitFor(() => expect(steps.textContent).toContain('Logline set · 1/5'))
    expect(steps.textContent).toContain('0 beats · 0 linked')
  })
})

describe('live sync', () => {
  it('opens one stream per project and refetches what an event touches', async () => {
    let version = 1
    const api = mockApi({
      'GET /api/v1/projects/3/storyline': () => storyline(version, version === 1 ? 'First logline' : 'Changed by an agent'),
      'GET /api/v1/projects/3/workspace': workspace(3),
      'GET /api/v1/projects/3/characters': [],
      'GET /api/v1/projects/3/beats': [],
    })
    renderAt('/projects/3/storyline')
    expect(await screen.findByDisplayValue('First logline')).toBeTruthy()
    const streams = FakeEventSource.open()
    expect(streams).toHaveLength(1)
    expect(streams[0].url).toBe('/api/v1/projects/3/events')
    version = 2
    act(() => streams[0].emit('project.changed', { version: 2 }))
    expect(await screen.findByDisplayValue('Changed by an agent')).toBeTruthy()
    expect(api.calls.filter(call => call.path === '/api/v1/projects/3/storyline').length).toBeGreaterThanOrEqual(2)
  })

  it('shares a single EventSource between subscribers', () => {
    const first = subscribeProjectEvents(9, () => undefined)
    const second = subscribeProjectEvents(9, () => undefined)
    expect(FakeEventSource.open()).toHaveLength(1)
    first()
    expect(FakeEventSource.open()).toHaveLength(1)
    second()
    expect(FakeEventSource.open()).toHaveLength(0)
  })

  it('maps events to the queries they make stale', () => {
    expect(staleKeysFor(3, { kind: 'story.changed', data: { kind: 'timeline_event' } })).toContainEqual(keys.timelines(3))
    expect(staleKeysFor(3, { kind: 'structure.changed', data: {} })).toContainEqual(keys.beats(3))
    expect(staleKeysFor(3, { kind: 'story.changed', data: { kind: 'beat' } })).toContainEqual(keys.visuals(3))
    expect(staleKeysFor(3, { kind: 'scene.changed', data: {} })).toContainEqual(keys.visuals(3))
    expect(staleKeysFor(3, { kind: 'project.changed', data: {} })).toContainEqual(keys.storyline(3))
    expect(staleKeysFor(3, { kind: 'run.changed', data: {} })).toEqual([keys.runs(3)])
    expect(staleKeysFor(3, { kind: 'rag.reindexed', data: {} })).toEqual([])
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    invalidateForEvent(client, 3, { kind: 'scene.changed', data: {} })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.workspaces(3) })
  })
})
