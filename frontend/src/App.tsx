import { useEffect, useState } from 'react'
import { createProject, listProjects, Project, ProjectCreatePayload } from './api'
import Workspace from './Workspace'

const genres = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Historical', 'Horror', 'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western', 'Experimental']
const languages = ['English', 'Hindi', 'Bengali', 'Telugu', 'Marathi', 'Tamil', 'Gujarati', 'Kannada', 'Malayalam', 'Punjabi', 'Odia', 'Assamese', 'Urdu', 'Kashmiri', 'Konkani', 'Nepali', 'Sindhi', 'Maithili', 'Sanskrit', 'Spanish', 'French', 'German', 'Italian', 'Portuguese', 'Japanese', 'Korean', 'Mandarin', 'Arabic']

type FormState = ProjectCreatePayload & { references: string; artwork_url: string }

const emptyForm: FormState = {
  title: '', logline: '', description: '', story_outline: '', visual_style: '',
  camera_type: 'Digital', screening_type: 'flat_1_85', artwork_url: '',
  genres: [], languages: [], references: '', primary_language: 'English',
}

function App() {
  const workspaceMatch = window.location.pathname.match(/^\/projects\/(\d+)$/)
  if (workspaceMatch) return <Workspace projectId={Number(workspaceMatch[1])} />

  const [projects, setProjects] = useState<Project[]>([])
  const [form, setForm] = useState<FormState>(emptyForm)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { void refresh() }, [])

  async function refresh() {
    try { setProjects(await listProjects()) } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load projects') }
  }

  function openWizard() { setForm(emptyForm); setStep(0); setError(''); setWizardOpen(true) }
  function toggle(field: 'genres' | 'languages', value: string) {
    setForm(current => ({ ...current, [field]: current[field].includes(value) ? current[field].filter(item => item !== value) : [...current[field], value] }))
  }
  function update(name: keyof FormState, value: string) { setForm(current => ({ ...current, [name]: value })) }

  async function submit() {
    if (!form.title.trim()) { setError('Give your project a title before continuing.'); setStep(0); return }
    setSaving(true); setError('')
    try {
      const { references: _references, ...payload } = form
      const created = await createProject(payload)
      setProjects(current => [...current, created].sort((a, b) => a.title.localeCompare(b.title)))
      setWizardOpen(false)
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create project') }
    finally { setSaving(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">✦</span><span className="wordmark"><em>Draft</em><b>Pilot</b></span></div><p className="eyebrow">Story studio</p><nav><a className="active">Projects <span>{projects.length}</span></a><a>Studio</a><a>Settings</a></nav><div className="sidebar-note"><span className="status-dot" /> Local workspace<br /><small>Your drafts stay close.</small></div></aside>
    <main className="main"><header className="topbar"><div><p className="eyebrow">Your workspace</p><h1>Projects</h1></div><button className="button primary" onClick={openWizard}>New project <span>＋</span></button></header>
      {error && <div className="notice">{error}<button onClick={() => setError('')}>×</button></div>}
      <section className="hero"><div><p className="eyebrow warm">MAKE SOMETHING WORTH WATCHING</p><h2>A clear desk for<br /><em>big stories.</em></h2><p>Build a world, shape its rhythm, and write the version only you can see.</p></div><div className="hero-orbit"><span>✦</span><span>SCENE / 01</span></div></section>
      <div className="section-heading"><div><p className="eyebrow">Library</p><h3>{projects.length ? 'Your projects' : 'Start your first story'}</h3></div><span className="count">{String(projects.length).padStart(2, '0')} projects</span></div>
      <section className="project-grid">{projects.map(project => <article className="project-card" key={project.id} onClick={() => window.location.assign(`/projects/${project.id}`)}><div className="card-art">{project.artwork_url ? <img src={project.artwork_url} alt="" /> : <span>{project.title.slice(0, 1).toUpperCase()}</span>}<small>OPEN PROJECT ↗</small></div><div className="card-copy"><div><h4>{project.title}</h4><p>{project.logline || 'A new story in progress.'}</p></div><span className="card-arrow">→</span></div>{project.genres.length > 0 && <div className="tags">{project.genres.slice(0, 3).map(genre => <span key={genre}>{genre}</span>)}</div>}</article>)}<button className="new-card" onClick={openWizard}><span>＋</span><strong>Begin a new project</strong><small>Start with a spark</small></button></section>
    </main>
    {wizardOpen && <div className="modal-backdrop"><form className="wizard" onSubmit={event => { event.preventDefault(); void submit() }}><div className="wizard-head"><div><p className="eyebrow warm">NEW PROJECT</p><h2>Find the shape<br />of your story.</h2></div><button type="button" className="close" onClick={() => setWizardOpen(false)}>×</button></div><div className="steps">{['Brief', 'World', 'References', 'Review'].map((label, index) => <button type="button" className={index === step ? 'selected' : index < step ? 'done' : ''} key={label} onClick={() => index <= step && setStep(index)}><span>0{index + 1}</span>{label}</button>)}</div><div className="wizard-body">{step === 0 && <><label>Project title<input autoFocus value={form.title} onChange={e => update('title', e.target.value)} placeholder="The name it has been waiting for" /></label><label>Logline<textarea value={form.logline ?? ''} onChange={e => update('logline', e.target.value)} placeholder="One sentence that holds the whole thing…" /></label><fieldset><legend>Genres</legend><div className="choice-grid">{genres.map(item => <button type="button" className={form.genres.includes(item) ? 'choice on' : 'choice'} onClick={() => toggle('genres', item)} key={item}>{item}</button>)}</div></fieldset></>}{step === 1 && <><label>Description<textarea value={form.description ?? ''} onChange={e => update('description', e.target.value)} placeholder="What is this project really about?" /></label><label>Story outline<textarea value={form.story_outline ?? ''} onChange={e => update('story_outline', e.target.value)} placeholder="Beginning, turning points, and ending…" /></label><div className="two-up"><label>Camera<select value={form.camera_type ?? ''} onChange={e => update('camera_type', e.target.value)}><option>Digital</option><option>Film</option><option>Animation</option><option>Mixed</option></select></label><label>Primary screenplay language<select value={form.primary_language} onChange={e => update('primary_language', e.target.value)}>{languages.map(item => <option key={item}>{item}</option>)}</select><span className="helper">Scene headings and action stay in this language.</span></label><label>Dialogue translation languages<div className="choice-grid">{languages.map(item => <button type="button" className={form.languages.includes(item) ? 'choice on' : 'choice'} onClick={() => toggle('languages', item)} key={item}>{item}</button>)}</div><span className="helper">Select any languages for dialogue translations. The original dialogue remains the source.</span></label></div></>}{step === 2 && <><label>Creative references<textarea value={form.references} onChange={e => update('references', e.target.value)} placeholder="Films, directors, places, or textures that belong in this world…" /></label><label>Artwork link<input value={form.artwork_url} onChange={e => update('artwork_url', e.target.value)} placeholder="https://…" /></label><p className="helper">You can add more references and upload artwork from the project workspace.</p></>}{step === 3 && <div className="review"><div className="review-art">{form.artwork_url ? <img src={form.artwork_url} alt="" /> : <span>{form.title.slice(0, 1).toUpperCase() || '✦'}</span>}</div><div><p className="eyebrow warm">READY TO BEGIN</p><h3>{form.title || 'Untitled project'}</h3><p>{form.logline || 'Your logline will appear here.'}</p><div className="tags">{form.genres.map(item => <span key={item}>{item}</span>)}</div></div></div>}</div><div className="wizard-foot"><button type="button" className="button quiet" onClick={() => step ? setStep(step - 1) : setWizardOpen(false)}>{step ? '← Back' : 'Cancel'}</button>{step < 3 ? <button type="button" className="button primary" onClick={() => form.title.trim() || step !== 0 ? setStep(step + 1) : setError('Give your project a title before continuing.')}>Continue <span>→</span></button> : <button type="button" className="button primary" onClick={() => void submit()} disabled={saving}>{saving ? 'Creating…' : 'Create project ✦'}</button>}</div></form></div>}
  </div>
}

export default App
