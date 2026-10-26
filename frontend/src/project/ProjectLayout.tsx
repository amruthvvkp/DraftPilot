import { Link, NavLink, Outlet } from 'react-router'
import { useProjectLiveSync } from '../data/liveSync'
import { useBeats, useCharacters, useStoryline, useWorkspace } from '../data/queries'
import { projectStages, type Stage } from './progress'
import { useProjectId } from './useProjectId'
import './project.css'

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
  return <div className="project-shell">
    <header className="project-bar">
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
      {/* G17 mounts the persistent AG-UI chat dock in this rail; until then the page-level chat panels stay where they are. */}
      <div className="project-chat-rail" id="chat-dock" data-slot="chat" />
    </div>
  </div>
}
