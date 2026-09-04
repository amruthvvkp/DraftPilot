import { useState } from 'react'
import { createProject, Project, ProjectCreatePayload, ProjectReferenceInput } from './api'

const genres = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Historical', 'Horror', 'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western', 'Experimental']
const languages = ['English', 'Hindi', 'Bengali', 'Telugu', 'Marathi', 'Tamil', 'Gujarati', 'Kannada', 'Malayalam', 'Punjabi', 'Odia', 'Assamese', 'Urdu', 'Kashmiri', 'Konkani', 'Nepali', 'Sindhi', 'Maithili', 'Sanskrit', 'Spanish', 'French', 'German', 'Italian', 'Portuguese', 'Japanese', 'Korean', 'Mandarin', 'Arabic']
const referenceKinds = [['film', 'Film'], ['director', 'Director'], ['style', 'Style'], ['reference_scene', 'Reference scene'], ['camera', 'Camera'], ['lighting', 'Lighting'], ['color_palette', 'Color palette'], ['location', 'Location'], ['other', 'Other']] as const

type FormState = Omit<ProjectCreatePayload, 'references'> & { references: ProjectReferenceInput[]; artwork_url: string }
type ProjectWizardProps = { onCreated: (project: Project) => void; onClose: () => void }

const emptyForm: FormState = { title: '', logline: '', description: '', story_outline: '', visual_style: '', camera_type: 'Digital', screening_type: 'flat_1_85', artwork_url: '', genres: [], languages: [], references: [], primary_language: 'English' }

export default function ProjectWizard({ onCreated, onClose }: ProjectWizardProps) {
  const [form, setForm] = useState<FormState>(emptyForm)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function update(name: keyof FormState, value: string): void {
    setForm(current => name === 'primary_language' ? { ...current, primary_language: value, languages: current.languages.filter(item => item !== value) } : { ...current, [name]: value })
  }

  function toggle(field: 'genres' | 'languages', value: string): void {
    if (field === 'languages' && value === form.primary_language) return
    setForm(current => ({ ...current, [field]: current[field].includes(value) ? current[field].filter(item => item !== value) : [...current[field], value] }))
  }

  function updateReference(index: number, field: keyof ProjectReferenceInput, value: string): void {
    setForm(current => ({ ...current, references: current.references.map((reference, referenceIndex) => referenceIndex === index ? { ...reference, [field]: value } : reference) }))
  }

  function addReference(): void {
    setForm(current => ({ ...current, references: [...current.references, { kind: 'film', label: '' }] }))
  }

  function removeReference(index: number): void {
    setForm(current => ({ ...current, references: current.references.filter((_, referenceIndex) => referenceIndex !== index) }))
  }

  async function submit(): Promise<void> {
    if (!form.title.trim()) { setError('Give your project a title before continuing.'); setStep(0); return }
    setSaving(true)
    setError('')
    try {
      const references = form.references.filter(reference => reference.label.trim()).map(reference => ({ ...reference, label: reference.label.trim(), url: reference.url?.trim() || null, note: reference.note?.trim() || null }))
      const created = await createProject({ ...form, title: form.title.trim(), artwork_url: form.artwork_url.trim() || null, references })
      onCreated(created)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create project')
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal-backdrop"><form className="wizard" onSubmit={event => event.preventDefault()}><div className="wizard-head"><div><p className="eyebrow warm">NEW PROJECT</p><h2>Find the shape<br />of your story.</h2></div><button type="button" className="close" onClick={onClose}>×</button></div><div className="steps">{['Brief', 'World', 'References', 'Review'].map((label, index) => <button type="button" className={index === step ? 'selected' : index < step ? 'done' : ''} key={label} onClick={() => index <= step && setStep(index)}><span>0{index + 1}</span>{label}</button>)}</div>
    <div className="wizard-body">
      {step === 0 && <><label>Project title<input autoFocus value={form.title} onChange={event => update('title', event.target.value)} placeholder="The name it has been waiting for" /></label><label>Logline<textarea value={form.logline ?? ''} onChange={event => update('logline', event.target.value)} placeholder="One sentence that holds the whole thing…" /></label><fieldset><legend>Genres</legend><div className="choice-grid">{genres.map(item => <button type="button" className={form.genres.includes(item) ? 'choice on' : 'choice'} onClick={() => toggle('genres', item)} key={item}>{item}</button>)}</div></fieldset></>}
      {step === 1 && <><label>Description<textarea value={form.description ?? ''} onChange={event => update('description', event.target.value)} placeholder="What is this project really about?" /></label><label>Story outline<textarea value={form.story_outline ?? ''} onChange={event => update('story_outline', event.target.value)} placeholder="Beginning, turning points, and ending…" /></label><div className="two-up"><label>Camera<select value={form.camera_type ?? ''} onChange={event => update('camera_type', event.target.value)}><option>Digital</option><option>Film</option><option>Animation</option><option>Mixed</option></select></label><label>Primary screenplay language<select value={form.primary_language} onChange={event => update('primary_language', event.target.value)}>{languages.map(item => <option key={item}>{item}</option>)}</select><span className="helper">Scene headings and action stay in this language.</span></label><label>Dialogue translation languages<div className="choice-grid">{languages.map(item => <button type="button" className={form.languages.includes(item) ? 'choice on' : 'choice'} onClick={() => toggle('languages', item)} key={item}>{item}</button>)}</div><span className="helper">The original dialogue remains the source.</span></label></div></>}
      {step === 2 && <><fieldset><legend>Typed creative references</legend>{form.references.map((reference, index) => <div className="reference-row" key={index}><label>Type<select value={reference.kind} onChange={event => updateReference(index, 'kind', event.target.value)}>{referenceKinds.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Reference<input value={reference.label} onChange={event => updateReference(index, 'label', event.target.value)} placeholder="Pather Panchali or a visual texture" /></label><label>URL<input value={reference.url ?? ''} onChange={event => updateReference(index, 'url', event.target.value)} placeholder="https://…" /></label><label>Note<input value={reference.note ?? ''} onChange={event => updateReference(index, 'note', event.target.value)} placeholder="Why it belongs" /></label><button type="button" className="mini-button" onClick={() => removeReference(index)}>Remove</button></div>)}{form.references.length === 0 && <p className="helper">Add films, directors, places, styles, or production references as separate typed entries.</p>}<button type="button" className="button quiet" onClick={addReference}>＋ Add typed reference</button></fieldset><label>Artwork link<input value={form.artwork_url} onChange={event => update('artwork_url', event.target.value)} placeholder="https://…" /></label><p className="helper">References remain editable and typed in the project workspace.</p></>}
      {step === 3 && <div className="review"><div className="review-art">{form.artwork_url ? <img src={form.artwork_url} alt="" /> : <span>{form.title.slice(0, 1).toUpperCase() || '✦'}</span>}</div><div><p className="eyebrow warm">READY TO BEGIN</p><h3>{form.title || 'Untitled project'}</h3><p>{form.logline || 'Your logline will appear here.'}</p><div className="tags">{form.genres.map(item => <span key={item}>{item}</span>)}</div><p>{form.references.filter(reference => reference.label.trim()).length} typed references</p></div></div>}
    </div><div className="wizard-foot"><button type="button" className="button quiet" onClick={() => step ? setStep(step - 1) : onClose()}>{step ? '← Back' : 'Cancel'}</button>{step < 3 ? <button type="button" className="button primary" onClick={() => form.title.trim() || step !== 0 ? setStep(step + 1) : setError('Give your project a title before continuing.')}>Continue <span>→</span></button> : <button type="button" className="button primary" onClick={() => void submit()} disabled={saving}>{saving ? 'Creating…' : 'Create project ✦'}</button>}</div>{error && <div className="notice">{error}</div>}</form></div>
}
