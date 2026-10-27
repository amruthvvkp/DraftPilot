import type { ComponentType } from 'react'
import { CharacterCard, type CardProps, GenericCard, OutlineCard, PlanCard, proposalIn, ProposalCard, SceneCard, SpecialistCard, WorkflowCard } from './cards'
import { parseJson, type ToolEntry } from './reducer'

type Rule = { match: (call: ToolEntry, args: Record<string, unknown>, result: unknown) => boolean; card: ComponentType<CardProps> }

/** Generative UI: which card renders which tool call. The first match wins; anything else gets the generic chip. */
export const TOOL_CARDS: Rule[] = [
  { match: call => call.name === 'plan', card: PlanCard },
  { match: (call, args) => call.name === 'read_character' || (call.name === 'create_story_entity' && args.kind === 'character'), card: CharacterCard },
  { match: call => call.name === 'read_outline' || call.name === 'propose_outline', card: OutlineCard },
  { match: call => call.name === 'start_room_workflow' || call.name === 'start_evaluation', card: WorkflowCard },
  { match: call => call.name === 'consult' || call.name === 'consult_many', card: SpecialistCard },
  { match: call => call.name === 'create_scene' || call.name === 'write_scene', card: SceneCard },
  { match: (call, _args, result) => call.name.startsWith('propose_') || proposalIn(result) !== null, card: ProposalCard },
]

/** Parsed arguments of a call (an object; streaming or malformed arguments read as empty). */
export function argsOf(call: ToolEntry): Record<string, unknown> {
  const parsed = parseJson(call.args)
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
}

/** Pick the card component for a tool call. */
export function cardFor(call: ToolEntry): ComponentType<CardProps> {
  const args = argsOf(call)
  const result = parseJson(call.result)
  return TOOL_CARDS.find(rule => rule.match(call, args, result))?.card ?? GenericCard
}

/** Render a tool call with its card. */
export function ToolCard({ call, projectId }: { call: ToolEntry; projectId: number }) {
  const Card = cardFor(call)
  return <Card call={call} args={argsOf(call)} result={parseJson(call.result)} projectId={projectId} />
}
