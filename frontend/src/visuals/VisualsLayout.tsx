import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router'
import { errorMessage, useStoryVisuals } from '../data/queries'
import type { StoryVisuals } from '../storyApi'
import { useProjectId } from '../project/useProjectId'
import './visuals.css'

export const VISUAL_TOOLS = [
  { path: 'tension', label: 'Tension curve' },
  { path: 'relationships', label: 'Relationship graph' },
  { path: 'corkboard', label: 'Corkboard' },
  { path: 'structure', label: 'Structure templates' },
  { path: 'pacing', label: 'Pacing heatmap' },
] as const

/** The visual tools shell: a sub-nav over the tools and the chosen tool. */
export default function VisualsLayout() {
  const base = `/projects/${useProjectId()}/visuals`
  return <main className="story-page visuals-page">
    <nav className="visuals-nav" aria-label="Visual tools">
      {VISUAL_TOOLS.map(tool => <NavLink key={tool.path} to={`${base}/${tool.path}`}>{tool.label}</NavLink>)}
    </nav>
    <Outlet />
  </main>
}

/** Load the visuals aggregate and render `children` with it, or the loading and error states. */
export function WithVisuals({ children }: { children: (visuals: StoryVisuals) => ReactNode }) {
  const { data, error } = useStoryVisuals(useProjectId())
  if (error) return <p className="notice" role="alert">{errorMessage(error, 'Unable to load the story data')}</p>
  if (!data) return <p className="empty-copy">Loading…</p>
  return <>{children(data)}</>
}

/** A visual tool's heading block. */
export function ToolHead({ title, children }: { title: string; children: ReactNode }) {
  return <header className="story-head">
    <p className="eyebrow warm">VISUAL TOOLS</p>
    <h1>{title}</h1>
    <p>{children}</p>
  </header>
}
