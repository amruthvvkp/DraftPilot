import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { mockApi } from '../test/harness'
import { CharacterCard, GenericCard, OutlineCard, PlanCard, ProposalCard, SceneCard, SpecialistCard, WorkflowCard } from './cards'
import type { ToolEntry } from './reducer'
import { cardFor, ToolCard } from './registry'

const call = (name: string, args: object = {}, result?: unknown, status: ToolEntry['status'] = 'done'): ToolEntry => ({
  kind: 'tool', id: `c-${name}`, name, args: JSON.stringify(args), status, result: result === undefined ? undefined : JSON.stringify(result),
})
const proposal = { id: 41, project_id: 3, run_id: null, target_kind: 'beat', target_id: 0, operation: {}, diff: { summary: 'Replace the outline (6 beats)' }, before: {}, base_version: 0, status: 'proposed' }

function show(entry: ToolEntry) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><ToolCard call={entry} projectId={3} /></MemoryRouter></QueryClientProvider>)
}

describe('generative UI registry', () => {
  it('maps tools to cards, falling back to the generic chip', () => {
    expect(cardFor(call('plan'))).toBe(PlanCard)
    expect(cardFor(call('read_character'))).toBe(CharacterCard)
    expect(cardFor(call('create_story_entity', { kind: 'character', fields: { name: 'Karl' } }))).toBe(CharacterCard)
    expect(cardFor(call('create_story_entity', { kind: 'location', fields: { name: 'Bank' } }))).toBe(GenericCard)
    expect(cardFor(call('read_outline'))).toBe(OutlineCard)
    expect(cardFor(call('propose_outline'))).toBe(OutlineCard)
    expect(cardFor(call('propose_story_change'))).toBe(ProposalCard)
    expect(cardFor(call('some_new_tool', {}, proposal))).toBe(ProposalCard)
    expect(cardFor(call('start_room_workflow'))).toBe(WorkflowCard)
    expect(cardFor(call('start_evaluation'))).toBe(WorkflowCard)
    expect(cardFor(call('consult_many'))).toBe(SpecialistCard)
    expect(cardFor(call('write_scene'))).toBe(SceneCard)
    expect(cardFor(call('read_project_overview'))).toBe(GenericCard)
  })

  it('renders a plan as a checklist', () => {
    show(call('plan', { goal: 'Develop the cast', steps: ['✓ Read the storyline', 'Draft the leads'] }, { goal: 'Develop the cast', steps: ['✓ Read the storyline', 'Draft the leads'], done: 1 }))
    expect((screen.getByRole('checkbox', { name: 'Read the storyline' }) as HTMLInputElement).checked).toBe(true)
    expect((screen.getByRole('checkbox', { name: 'Draft the leads' }) as HTMLInputElement).checked).toBe(false)
  })

  it('renders a created character with a link to their profile', () => {
    show(call('create_story_entity', { kind: 'character', fields: { name: 'Karl' } }, { id: 7, name: 'Karl', role: 'supporting', want: 'To be seen' }))
    expect(screen.getByText('New character: Karl')).toBeTruthy()
    expect(screen.getByText('To be seen')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open Karl ↗' }).getAttribute('href')).toBe('/projects/3/characters/7')
  })

  it('renders an outline as acts and beats, and a proposed outline with its decision', async () => {
    const api = mockApi({ 'POST /api/v1/projects/3/agent-proposals/41/approve': { ...proposal, status: 'approved' } })
    show(call('propose_outline', { beats: [{ act: 1, title: 'Wedding toast' }, { act: 2, title: 'Spectre', summary: 'A town too perfect' }] }, proposal))
    expect(screen.getByText('Act 1')).toBeTruthy()
    expect(screen.getByText('Spectre')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Approve proposal' }))
    expect(await screen.findByText('approved')).toBeTruthy()
    expect(api.calls.map(item => `${item.method} ${item.path}`)).toContain('POST /api/v1/projects/3/agent-proposals/41/approve')
  })

  it('lets the writer reject a proposal from its card', async () => {
    mockApi({ 'POST /api/v1/projects/3/agent-proposals/41/reject': { ...proposal, status: 'rejected' } })
    show(call('propose_story_change', { summary: 'Rename Will' }, proposal))
    expect(screen.getByText('Replace the outline (6 beats)')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))
    expect(await screen.findByText('rejected')).toBeTruthy()
  })

  it('follows a started workflow run until it finishes', async () => {
    let polls = 0
    mockApi({
      'GET /api/v1/projects/3/runs/12': () => {
        polls += 1
        return { id: 12, project_id: 3, kind: 'room_workflow', status: polls > 1 ? 'succeeded' : 'running', result: { trail: [{ step: 'storyline', role: 'story_architect' }] }, error: null, attempt_count: 1, max_attempts: 3 }
      },
    })
    show(call('start_room_workflow', { workflow: 'develop_story' }, { id: 12, status: 'queued' }))
    expect(await screen.findByText(/stage: storyline/)).toBeTruthy()
    expect(screen.getByText('Story architect')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('succeeded')).toBeTruthy(), { timeout: 4000 })
  })

  it('shows consulted specialists as chips with their answers', () => {
    show(call('consult_many', { requests: [{ role: 'character_specialist', brief: 'Arcs' }, { role: 'continuity_supervisor', brief: 'Facts' }] }, ['[Character specialist] Will needs Edward.', '[Continuity] Fine.']))
    expect(screen.getByText('Character specialist ✓')).toBeTruthy()
    expect(screen.getByText('Continuity supervisor ✓')).toBeTruthy()
    expect(screen.getByText('[Character specialist] Will needs Edward.')).toBeTruthy()
  })

  it('links a written scene into the script', () => {
    show(call('create_scene', { heading: 'INT. BANK - DAY' }, { id: 70, heading: 'INT. BANK - DAY', act_id: 4, version: 1 }))
    expect(screen.getByRole('link', { name: 'Open INT. BANK - DAY ↗' }).getAttribute('href')).toBe('/projects/3?scene=70')
  })

  it('falls back to a chip with the raw call', () => {
    show(call('read_project_overview', { project_id: 3 }, { project: { title: 'Big Fish' } }))
    expect(screen.getByText('Read the project overview ✓')).toBeTruthy()
    expect(screen.getByText(/"Big Fish"/)).toBeTruthy()
  })
})
