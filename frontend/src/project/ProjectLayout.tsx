import { lazy, Suspense, useEffect, useRef } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
import { readDockOpen } from '../chat/dockState'
import { useProjectLiveSync } from '../data/liveSync'
import { useBeats, useCharacters, useStoryline, useWorkspace } from '../data/queries'
import { projectStages, type Stage } from './progress'
import { useProjectId } from './useProjectId'
import './project.css'

// The dock (AG-UI client, Markdown) loads in its own chunk so the studio itself stays light.
const ChatDock = lazy(() => import('../chat/ChatDock'))

const STATE_MARK: Record<Stage['state'], string> = { empty: '○', started: '◐', done: '●' }
const STATE_TEXT: Record<Stage['state'], string> = { empty: 'not started', started: 'in progress', done: 'complete' }

/** One step of the guided stepper, with its completion. */
function StepLink({ stage, index }: { stage: Stage; index: number }) {
  return <NavLink to={stage.to} end={stage.key === 'script'} className={({ isActive }) => `project-step ${stage.state}${isActive ? ' active' : ''}`}>
    <span className="project-step-mark" aria-hidden="true">{STATE_MARK[stage.state]}</span>
    <span className="project-step-copy">
      <strong>{index + 1}. {stage.label}</strong>
      <small>{stage.summary}<span className="visually-hidden"> ({STATE_TEXT[stage.state]})</span></small>
    </span>
  </NavLink>
}

/** The project shell: a guided stepper over every project page, live sync, and the chat dock slot. */
export default function ProjectLayout() {
  const projectId = useProjectId()
  useProjectLiveSync(projectId)
  const storyline = useStoryline(projectId).data
  const characters = useCharacters(projectId).data
  const beats = useBeats(projectId).data
  const workspace = useWorkspace(projectId).data
  const stages = projectStages({ projectId, storyline, characters, beats, workspace })
  const base = `/projects/${projectId}`
  const shell = useRef<HTMLDivElement>(null)
  const bar = useRef<HTMLElement>(null)
  // The dock sits under the sticky bar; keep its offset equal to the bar's (it wraps on narrow screens).
  useEffect(() => {
    const element = bar.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => shell.current?.style.setProperty('--project-bar-height', `${element.offsetHeight}px`))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return <div className="project-shell" ref={shell}>
    <header className="project-bar" ref={bar}>
      <Link className="project-bar-home" to="/projects">All projects</Link>
      <strong className="project-bar-title">{storyline?.title ?? workspace?.project.title ?? ''}</strong>
      <nav className="project-steps" aria-label="Project steps">
        {stages.map((stage, index) => <StepLink key={stage.key} stage={stage} index={index} />)}
      </nav>
      <nav className="project-tools" aria-label="Studio tools">
        <NavLink to={`${base}/context-map`}>Context map</NavLink>
        <NavLink to={`${base}/locations`}>Locations</NavLink>
        <NavLink to={`${base}/twin`}>Story twin</NavLink>
        <NavLink to={`${base}/room`}>Writers’ room</NavLink>
        <NavLink to={`${base}/studio`}>Story studio</NavLink>
        <NavLink to={`${base}/context`}>Knowledge graph</NavLink>
      </nav>
    </header>
    <div className="project-body">
      <div className="project-main"><Outlet /></div>
      <div className="project-chat-rail" id="chat-dock"><Suspense fallback={<div className={readDockOpen() ? 'chat-dock-placeholder open' : 'chat-dock-placeholder'} />}><ChatDock projectId={projectId} /></Suspense></div>
    </div>
  </div>
}
