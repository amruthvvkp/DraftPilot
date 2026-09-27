import { useEffect, useState } from 'react'
import { DeletedProject, deleteProject, duplicateProject, getWriterProfile, listDeletedProjects, listProjects, Project, restoreProjectBackup } from './api'
import { normalizeAppearance, saveAppearance } from './theme'
import ArtifactStudio from './ArtifactStudio'
import KnowledgeGraphPage from './KnowledgeGraph'
import ProjectWizard from './ProjectWizard'
import ProviderSettings from './ProviderSettings'
import StoryTwinPage from './StoryTwin'
import Workspace from './Workspace'
import WritersRoom from './WritersRoom'

export default function App() {
  useEffect(() => {
    getWriterProfile().then(profile => { if (profile.preferences?.appearance) saveAppearance(normalizeAppearance(profile.preferences.appearance)) }).catch(() => undefined)
  }, [])
  const path = window.location.pathname
  const workspaceMatch = path.match(/^\/projects\/(\d+)$/)
  const artifactMatch = path.match(/^\/projects\/(\d+)\/studio$/)
  const contextMatch = path.match(/^\/projects\/(\d+)\/context$/)
  const roomMatch = path.match(/^\/projects\/(\d+)\/room$/)
  const twinMatch = path.match(/^\/projects\/(\d+)\/twin$/)
  if (workspaceMatch) return <Workspace projectId={Number(workspaceMatch[1])} />
  if (artifactMatch) return <ArtifactStudio projectId={Number(artifactMatch[1])} />
  if (contextMatch) return <KnowledgeGraphPage projectId={Number(contextMatch[1])} />
  if (roomMatch) return <WritersRoom projectId={Number(roomMatch[1])} />
  if (twinMatch) return <StoryTwinPage projectId={Number(twinMatch[1])} />
  if (path === '/settings') return <ProviderSettings />
  return <ProjectVault />
}

function ProjectVault() {
  const [projects, setProjects] = useState<Project[]>([])
  const [wizardOpen, setWizardOpen] = useState(false)
  const [error, setError] = useState('')
  const [profileName, setProfileName] = useState<string>('')
  const [deleted, setDeleted] = useState<DeletedProject[]>([])
  const [confirming, setConfirming] = useState<Project | null>(null)
  const [menuFor, setMenuFor] = useState<number | null>(null)
  const [notice, setNotice] = useState('')

  async function refresh(): Promise<void> {
    try { setProjects(await listProjects()) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load projects') }
    listDeletedProjects().then(setDeleted).catch(() => setDeleted([]))
  }

  async function duplicate(project: Project): Promise<void> {
    setMenuFor(null)
    try { const copy = await duplicateProject(project.id); setNotice(`Duplicated as “${copy.title}”.`); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to duplicate project') }
  }

  async function remove(project: Project): Promise<void> {
    try { await deleteProject(project.id); setConfirming(null); setNotice(`Deleted “${project.title}”. A backup was kept — restore it below.`); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to delete project') }
  }

  async function restore(item: DeletedProject): Promise<void> {
    try { await restoreProjectBackup(item.project_id, item.filename); setNotice(`Restored “${item.title}”.`); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to restore project') }
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

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">✦</span><span className="wordmark"><em>Draft</em><b>Pilot</b></span></div><p className="eyebrow">Story studio</p><nav><a className="active" href="/projects">Projects <span>{projects.length}</span></a><a href="/projects">Studio</a><a href="/settings">Settings</a></nav><div className="sidebar-note"><span className="status-dot" /> Local workspace<br /><small>Your drafts stay close.</small></div></aside><main className="main"><header className="topbar"><div><p className="eyebrow">Your workspace</p><h1>Projects</h1></div><div className="topbar-actions"><a href="/settings" className="user-profile-link" title="Writer Profile & Settings"><span className="user-avatar">{profileName ? profileName.slice(0, 1).toUpperCase() : 'W'}</span><span className="user-name">{profileName || 'Writer'}</span></a><button className="button primary" onClick={openWizard}>New project <span>＋</span></button></div></header>{error && <div className="notice">{error}<button onClick={() => setError('')}>×</button></div>}{notice && <div className="success-notice vault-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}<section className="hero"><div><p className="eyebrow warm">MAKE SOMETHING WORTH WATCHING</p><h2>A clear desk for<br /><em>big stories.</em></h2><p>Build a world, shape its rhythm, and write the version only you can see.</p></div><div className="hero-orbit"><span>✦</span><span>SCENE / 01</span></div></section><div className="section-heading"><div><p className="eyebrow">Library</p><h3>{projects.length ? 'Your projects' : 'Start your first story'}</h3></div><span className="count">{String(projects.length).padStart(2, '0')} projects</span></div><section className="project-grid">{projects.map(project => <article className="project-card" key={project.id} onClick={() => window.location.assign(`/projects/${project.id}`)}><div className="card-art">{project.artwork_url ? <img src={project.artwork_url} alt="" /> : <span>{project.title.slice(0, 1).toUpperCase()}</span>}<small>OPEN PROJECT ↗</small></div><div className="card-copy"><div><h4>{project.title}</h4><p>{project.logline || 'A new story in progress.'}</p></div><span className="card-arrow">→</span></div><div className="card-menu" onClick={event => event.stopPropagation()}><button className="card-menu-button" aria-label={`Actions for ${project.title}`} aria-expanded={menuFor === project.id} onClick={() => setMenuFor(menuFor === project.id ? null : project.id)}>⋯</button>{menuFor === project.id && <div className="card-menu-list" role="menu"><button role="menuitem" onClick={() => void duplicate(project)}>Duplicate</button><button role="menuitem" className="danger" onClick={() => { setMenuFor(null); setConfirming(project) }}>Delete…</button></div>}</div>{project.genres.length > 0 && <div className="tags">{project.genres.slice(0, 3).map(genre => <span key={genre}>{genre}</span>)}</div>}</article>)}<button className="new-card" onClick={openWizard}><span>＋</span><strong>Begin a new project</strong><small>Start with a spark</small></button></section>{deleted.length > 0 && <section className="deleted-projects" aria-label="Recently deleted"><div className="section-heading"><div><p className="eyebrow">Recovery</p><h3>Recently deleted</h3></div></div>{deleted.map(item => <article className="deleted-row" key={item.filename}><div><strong>{item.title}</strong><small>Deleted {new Date(item.deleted_at).toLocaleString()} · kept as a backup</small></div><button className="button quiet" onClick={() => void restore(item)}>Restore</button></article>)}</section>}</main>{confirming && <DeleteDialog project={confirming} onCancel={() => setConfirming(null)} onConfirm={() => void remove(confirming)} />}{wizardOpen && <ProjectWizard onCreated={handleCreated} onClose={() => setWizardOpen(false)} />}</div>
}

function DeleteDialog({ project, onCancel, onConfirm }: { project: Project; onCancel: () => void; onConfirm: () => void }) {
  const [typed, setTyped] = useState('')
  return <div className="modal-backdrop" role="presentation" onClick={onCancel}><section className="wizard delete-dialog" role="dialog" aria-modal="true" aria-label={`Delete ${project.title}`} onClick={event => event.stopPropagation()}>
    <p className="eyebrow warm">DELETE PROJECT</p><h2>Delete “{project.title}”?</h2>
    <p>Every draft, scene, artifact, run and proposal in this project is removed. DraftPilot keeps a backup first, so you can restore it from <strong>Recently deleted</strong>.</p>
    <label>Type the project title to confirm<input autoFocus value={typed} onChange={event => setTyped(event.target.value)} aria-label="Project title to confirm" /></label>
    <div className="dialog-actions"><button className="button quiet" onClick={onCancel}>Cancel</button><button className="button danger" disabled={typed.trim() !== project.title.trim()} onClick={onConfirm}>Delete project</button></div>
  </section></div>
}
