import { useEffect, useState } from 'react'
import { getWriterProfile, listProjects, Project } from './api'
import ArtifactStudio from './ArtifactStudio'
import KnowledgeGraphPage from './KnowledgeGraph'
import ProjectWizard from './ProjectWizard'
import ProviderSettings from './ProviderSettings'
import Workspace from './Workspace'

export default function App() {
  const path = window.location.pathname
  const workspaceMatch = path.match(/^\/projects\/(\d+)$/)
  const artifactMatch = path.match(/^\/projects\/(\d+)\/studio$/)
  const contextMatch = path.match(/^\/projects\/(\d+)\/context$/)
  if (workspaceMatch) return <Workspace projectId={Number(workspaceMatch[1])} />
  if (artifactMatch) return <ArtifactStudio projectId={Number(artifactMatch[1])} />
  if (contextMatch) return <KnowledgeGraphPage projectId={Number(contextMatch[1])} />
  if (path === '/settings') return <ProviderSettings />
  return <ProjectVault />
}

function ProjectVault() {
  const [projects, setProjects] = useState<Project[]>([])
  const [wizardOpen, setWizardOpen] = useState(false)
  const [error, setError] = useState('')
  const [profileName, setProfileName] = useState<string>('')

  async function refresh(): Promise<void> {
    try { setProjects(await listProjects()) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load projects') }
  }

  useEffect(() => {
    void refresh()
    getWriterProfile().then(profile => { if (profile.pen_name || profile.name) setProfileName(profile.pen_name || profile.name) }).catch(() => undefined)
  }, [])

  function handleCreated(project: Project): void {
    setProjects(current => [...current, project].sort((a, b) => a.title.localeCompare(b.title)))
    setWizardOpen(false)
    window.location.assign(`/projects/${project.id}`)
  }

  function openWizard(): void { setError(''); setWizardOpen(true) }

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">✦</span><span className="wordmark"><em>Draft</em><b>Pilot</b></span></div><p className="eyebrow">Story studio</p><nav><a className="active" href="/projects">Projects <span>{projects.length}</span></a><a href="/projects">Studio</a><a href="/settings">Settings</a></nav><div className="sidebar-note"><span className="status-dot" /> Local workspace<br /><small>Your drafts stay close.</small></div></aside><main className="main"><header className="topbar"><div><p className="eyebrow">Your workspace</p><h1>Projects</h1></div><div className="topbar-actions"><a href="/settings" className="user-profile-link" title="Writer Profile & Settings"><span className="user-avatar">{profileName ? profileName.slice(0, 1).toUpperCase() : 'W'}</span><span className="user-name">{profileName || 'Writer'}</span></a><button className="button primary" onClick={openWizard}>New project <span>＋</span></button></div></header>{error && <div className="notice">{error}<button onClick={() => setError('')}>×</button></div>}<section className="hero"><div><p className="eyebrow warm">MAKE SOMETHING WORTH WATCHING</p><h2>A clear desk for<br /><em>big stories.</em></h2><p>Build a world, shape its rhythm, and write the version only you can see.</p></div><div className="hero-orbit"><span>✦</span><span>SCENE / 01</span></div></section><div className="section-heading"><div><p className="eyebrow">Library</p><h3>{projects.length ? 'Your projects' : 'Start your first story'}</h3></div><span className="count">{String(projects.length).padStart(2, '0')} projects</span></div><section className="project-grid">{projects.map(project => <article className="project-card" key={project.id} onClick={() => window.location.assign(`/projects/${project.id}`)}><div className="card-art">{project.artwork_url ? <img src={project.artwork_url} alt="" /> : <span>{project.title.slice(0, 1).toUpperCase()}</span>}<small>OPEN PROJECT ↗</small></div><div className="card-copy"><div><h4>{project.title}</h4><p>{project.logline || 'A new story in progress.'}</p></div><span className="card-arrow">→</span></div>{project.genres.length > 0 && <div className="tags">{project.genres.slice(0, 3).map(genre => <span key={genre}>{genre}</span>)}</div>}</article>)}<button className="new-card" onClick={openWizard}><span>＋</span><strong>Begin a new project</strong><small>Start with a spark</small></button></section></main>{wizardOpen && <ProjectWizard onCreated={handleCreated} onClose={() => setWizardOpen(false)} />}</div>
}
