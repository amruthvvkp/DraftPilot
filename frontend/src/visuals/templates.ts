import type { Beat, BeatFields } from '../storyApi'

/** One target beat of a structure template: where it lands (0…1 of the runtime), in which act, and its outline type. */
export type TemplateBeat = { title: string; beat_type: string; act: number; at: number; summary: string }
export type StructureTemplate = { id: string; name: string; acts: string[]; beats: TemplateBeat[] }

/** Static structure templates. Applying one only ever creates beats through the normal API, after the writer confirms. */
export const TEMPLATES: StructureTemplate[] = [
  {
    id: 'save-the-cat',
    name: 'Save the Cat',
    acts: ['Act One', 'Act Two', 'Act Three'],
    beats: [
      { title: 'Opening Image', beat_type: 'opening_image', act: 0, at: 0, summary: 'A snapshot of the hero’s world before the story changes it.' },
      { title: 'Theme Stated', beat_type: 'setup', act: 0, at: 0.05, summary: 'Someone hints at what the hero needs to learn.' },
      { title: 'Set-Up', beat_type: 'setup', act: 0, at: 0.01, summary: 'The hero’s life, flaws and what is missing.' },
      { title: 'Catalyst', beat_type: 'inciting_incident', act: 0, at: 0.1, summary: 'The event that knocks the hero’s life off course.' },
      { title: 'Debate', beat_type: 'beat', act: 0, at: 0.11, summary: 'The hero hesitates: should they go?' },
      { title: 'Break into Two', beat_type: 'plot_point', act: 1, at: 0.2, summary: 'The hero chooses to enter the new world.' },
      { title: 'B Story', beat_type: 'beat', act: 1, at: 0.22, summary: 'A new relationship that carries the theme.' },
      { title: 'Fun and Games', beat_type: 'beat', act: 1, at: 0.25, summary: 'The promise of the premise, played out.' },
      { title: 'Midpoint', beat_type: 'midpoint', act: 1, at: 0.5, summary: 'A false victory or false defeat raises the stakes.' },
      { title: 'Bad Guys Close In', beat_type: 'pinch', act: 1, at: 0.55, summary: 'Pressure mounts from outside and within.' },
      { title: 'All Is Lost', beat_type: 'crisis', act: 1, at: 0.75, summary: 'The lowest point; something or someone is lost.' },
      { title: 'Dark Night of the Soul', beat_type: 'crisis', act: 1, at: 0.77, summary: 'The hero wallows, then finds the lesson.' },
      { title: 'Break into Three', beat_type: 'plot_point', act: 2, at: 0.8, summary: 'A new idea, born of A and B stories, points the way.' },
      { title: 'Finale', beat_type: 'climax', act: 2, at: 0.82, summary: 'The hero applies the lesson and confronts the problem.' },
      { title: 'Final Image', beat_type: 'resolution', act: 2, at: 1, summary: 'The opening image, changed.' },
    ].sort((a, b) => a.at - b.at),
  },
  {
    id: 'heros-journey',
    name: 'Hero’s Journey',
    acts: ['Departure', 'Initiation', 'Return'],
    beats: [
      { title: 'Ordinary World', beat_type: 'opening_image', act: 0, at: 0, summary: 'The hero at home, before the adventure.' },
      { title: 'Call to Adventure', beat_type: 'inciting_incident', act: 0, at: 0.1, summary: 'A challenge or quest appears.' },
      { title: 'Refusal of the Call', beat_type: 'beat', act: 0, at: 0.15, summary: 'Fear or duty holds the hero back.' },
      { title: 'Meeting the Mentor', beat_type: 'beat', act: 0, at: 0.2, summary: 'Advice, a gift or training prepares the hero.' },
      { title: 'Crossing the Threshold', beat_type: 'plot_point', act: 1, at: 0.25, summary: 'The hero commits and enters the special world.' },
      { title: 'Tests, Allies, Enemies', beat_type: 'beat', act: 1, at: 0.3, summary: 'The rules of the new world, learned the hard way.' },
      { title: 'Approach to the Inmost Cave', beat_type: 'pinch', act: 1, at: 0.45, summary: 'Preparing for the central ordeal.' },
      { title: 'Ordeal', beat_type: 'midpoint', act: 1, at: 0.5, summary: 'A life-or-death crisis; the hero faces their greatest fear.' },
      { title: 'Reward', beat_type: 'beat', act: 1, at: 0.6, summary: 'Having survived, the hero seizes the prize.' },
      { title: 'The Road Back', beat_type: 'plot_point', act: 2, at: 0.75, summary: 'The hero turns for home, and consequences follow.' },
      { title: 'Resurrection', beat_type: 'climax', act: 2, at: 0.9, summary: 'A final test where everything is at stake.' },
      { title: 'Return with the Elixir', beat_type: 'resolution', act: 2, at: 1, summary: 'The hero comes home changed, bringing something back.' },
    ],
  },
  {
    id: 'five-acts',
    name: 'Five acts',
    acts: ['Exposition', 'Rising action', 'Climax', 'Falling action', 'Dénouement'],
    beats: [
      { title: 'Exposition', beat_type: 'setup', act: 0, at: 0, summary: 'Who, where and what is at stake.' },
      { title: 'Inciting moment', beat_type: 'inciting_incident', act: 0, at: 0.15, summary: 'The conflict begins.' },
      { title: 'Rising action', beat_type: 'beat', act: 1, at: 0.25, summary: 'Complications build toward the turn.' },
      { title: 'Climax', beat_type: 'climax', act: 2, at: 0.5, summary: 'The turning point; the hero’s fortunes reverse.' },
      { title: 'Falling action', beat_type: 'beat', act: 3, at: 0.7, summary: 'The consequences of the turn play out.' },
      { title: 'Final suspense', beat_type: 'crisis', act: 3, at: 0.85, summary: 'One last doubt about the outcome.' },
      { title: 'Dénouement', beat_type: 'resolution', act: 4, at: 1, summary: 'Loose ends tied; a new normal.' },
    ],
  },
]

export type TemplateMatch = { target: TemplateBeat; beat: Beat | null }

const normal = (text: string) => text.trim().toLocaleLowerCase()

/**
 * Match each target beat to one of the writer's beats: first by title, then by a shared structural
 * `beat_type` (never the plain "beat" type). Each beat matches at most one target.
 */
export function matchTemplate(template: StructureTemplate, beats: Beat[]): TemplateMatch[] {
  const used = new Set<number>()
  const byTitle = template.beats.map(target => {
    const beat = beats.find(item => !used.has(item.id) && normal(item.title) === normal(target.title)) ?? null
    if (beat) used.add(beat.id)
    return beat
  })
  return template.beats.map((target, index) => {
    let beat = byTitle[index]
    if (!beat && target.beat_type !== 'beat') {
      beat = beats.find(item => !used.has(item.id) && item.beat_type === target.beat_type) ?? null
      if (beat) used.add(beat.id)
    }
    return { target, beat }
  })
}

/** The project act a template act lands in: same index, else the last act; null when the draft has no acts. */
export function actFor(templateAct: number, actIds: number[]): number | null {
  return actIds.length ? actIds[Math.min(templateAct, actIds.length - 1)] : null
}

/** The create-beat payloads for the unmatched targets, appended after each act's existing beats in template order. */
export function planTemplateBeats(matches: TemplateMatch[], beats: Beat[], actIds: number[]): (BeatFields & { title: string })[] {
  const next = new Map<number | null, number>()
  const known = new Set(actIds)
  for (const beat of beats) {
    const column = beat.act_id !== null && known.has(beat.act_id) ? beat.act_id : null
    next.set(column, Math.max(next.get(column) ?? 0, beat.position + 1))
  }
  return matches.filter(match => !match.beat).map(({ target }) => {
    const act_id = actFor(target.act, actIds)
    const position = next.get(act_id) ?? 0
    next.set(act_id, position + 1)
    return { title: target.title, summary: target.summary, beat_type: target.beat_type, act_id, position, status: 'planned' }
  })
}
