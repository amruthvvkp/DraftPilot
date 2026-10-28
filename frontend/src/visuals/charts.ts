import type { StoryVisuals, VisualEdge, VisualScene } from '../storyApi'

export const INTENSITY_MIN = -5
export const INTENSITY_MAX = 5

export type Point = { x: number; y: number; scene: VisualScene }

/** Map an intensity (−5…+5) to a y coordinate inside `height` (high is up), keeping `pad` clear. */
export function intensityY(value: number, height: number, pad = 0): number {
  const clamped = Math.max(INTENSITY_MIN, Math.min(INTENSITY_MAX, value))
  return pad + (INTENSITY_MAX - clamped) / (INTENSITY_MAX - INTENSITY_MIN) * (height - 2 * pad)
}

/** The x coordinate of the `index`th of `count` evenly spaced scenes across `width`. */
export function sceneX(index: number, count: number, width: number, pad = 0): number {
  return count <= 1 ? width / 2 : pad + index / (count - 1) * (width - 2 * pad)
}

/** Points of the tension curve, split into runs wherever a scene has no intensity (no events). */
export function tensionRuns(scenes: VisualScene[], width: number, height: number, pad = 0): Point[][] {
  const runs: Point[][] = []
  let run: Point[] = []
  for (const scene of scenes) {
    if (scene.intensity === null) {
      if (run.length) runs.push(run)
      run = []
      continue
    }
    run.push({ x: sceneX(scene.index, scenes.length, width, pad), y: intensityY(scene.intensity, height, pad), scene })
  }
  if (run.length) runs.push(run)
  return runs
}

/** An SVG path through a run of points. */
export function linePath(points: { x: number; y: number }[]): string {
  return points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

/** Where each act starts on the curve: the index of its first scene. */
export function actStarts(visuals: Pick<StoryVisuals, 'acts' | 'scenes'>): { id: number; title: string; index: number }[] {
  return visuals.acts.flatMap(act => {
    const first = visuals.scenes.find(scene => scene.act_id === act.id)
    return first ? [{ id: act.id, title: act.title, index: first.index }] : []
  })
}

/** Background colour for an intensity cell: cool for lows, warm for highs, neutral at 0 or without data. */
export function intensityColor(value: number | null): string {
  if (value === null) return 'var(--surface-3)'
  const strength = Math.round(Math.min(1, Math.abs(value) / INTENSITY_MAX) * 85)
  const hue = value < 0 ? 'var(--chart-low, #3b6fb6)' : 'var(--chart-high, #c8553d)'
  return value === 0 ? 'var(--line)' : `color-mix(in srgb, ${hue} ${strength}%, var(--surface))`
}

/** Format an intensity for people: signed, one decimal, or an em dash when unknown. */
export function formatIntensity(value: number | null): string {
  if (value === null) return '—'
  const rounded = Math.round(value * 10) / 10
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

/** Format seconds as m:ss. */
export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`
}

export type PacingAct = {
  id: number
  title: string
  runtime: number
  share: number
  intensity: number | null
  peak: number | null
  scenes: (VisualScene & { share: number })[]
}

/** Group scenes by act for the heatmap: each scene's share of its act's runtime, the act's share of the draft, its runtime-weighted average and its peak. */
export function pacingByAct(visuals: Pick<StoryVisuals, 'acts' | 'scenes' | 'total_runtime_seconds'>): PacingAct[] {
  const total = visuals.total_runtime_seconds || 1
  return visuals.acts.map(act => {
    const scenes = visuals.scenes.filter(scene => scene.act_id === act.id)
    const runtime = scenes.reduce((sum, scene) => sum + scene.runtime_seconds, 0)
    const rated = scenes.filter(scene => scene.intensity !== null)
    const weight = rated.reduce((sum, scene) => sum + scene.runtime_seconds, 0)
    const intensity = weight ? rated.reduce((sum, scene) => sum + (scene.intensity ?? 0) * scene.runtime_seconds, 0) / weight : null
    const peak = rated.length ? rated.reduce((best, scene) => Math.abs(scene.intensity ?? 0) > Math.abs(best) ? scene.intensity ?? 0 : best, 0) : null
    return {
      id: act.id, title: act.title, runtime, share: runtime / total, intensity, peak,
      scenes: scenes.map(scene => ({ ...scene, share: runtime ? scene.runtime_seconds / runtime : 0 })),
    }
  })
}

/** Place `count` nodes evenly on a circle, starting at the top. */
export function circleLayout(count: number, cx: number, cy: number, radius: number): { x: number; y: number }[] {
  if (count === 1) return [{ x: cx, y: cy }]
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + index / count * 2 * Math.PI
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
  })
}

/** An edge's strength: shared moments count fully; shared scenes count a quarter, so moments dominate. */
export function edgeStrength(edge: VisualEdge): number {
  return edge.shared_moments + edge.shared_scenes / 4
}

/** Stroke width for an edge relative to the strongest edge (1…8px; named-only links stay hairlines). */
export function edgeWidth(edge: VisualEdge, strongest: number): number {
  const strength = edgeStrength(edge)
  return strength && strongest ? 1 + 7 * strength / strongest : 1
}
