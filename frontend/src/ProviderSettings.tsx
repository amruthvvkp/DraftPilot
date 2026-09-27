import { type FormEvent, useEffect, useState } from 'react'
import AppearancePanel from './AppearancePanel'
import { addWriterMemory, createProviderProfile, forgetWriterMemory, getWriterProfile, listDefaultModels, listProfileModels, listProviderProfiles, listWriterMemories, ModelOption, ProviderProfile, saveWriterProfile, testProviderProfile, updateProviderProfile, WriterMemory, WriterProfile } from './api'
import CopilotPanel from './CopilotPanel'
import './provider-settings.css'

const initial = { name: '', provider: 'lm_studio', model: 'auto', base_url: '', api_key: '', enabled: true }

export default function ProviderSettings() {
  const [profiles, setProfiles] = useState<ProviderProfile[]>([])
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState<number | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [defaultModels, setDefaultModels] = useState<ModelOption[] | null>(null)
  const [defaultModelsError, setDefaultModelsError] = useState('')
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])

  async function refresh(): Promise<void> {
    try { setProfiles(await listProviderProfiles()) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load providers') }
  }
  useEffect(() => {
    void refresh()
    listDefaultModels()
      .then(models => { setDefaultModels(models); setModelOptions(models) })
      .catch(reason => setDefaultModelsError(reason instanceof Error ? reason.message : 'Default model server unreachable'))
  }, [])
  async function loadModels(profile: ProviderProfile): Promise<void> {
    setError('')
    try { const models = await listProfileModels(profile.id); setModelOptions(models); setMessage(`${profile.name}: ${models.length} models (${models.filter(item => item.loaded).length} loaded)`) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to list models') }
  }
  function update(field: keyof typeof initial, value: string | boolean): void { setForm(current => ({ ...current, [field]: value })) }
  function edit(profile: ProviderProfile): void {
    setEditing(profile.id); setForm({ name: profile.name, provider: profile.provider, model: profile.model, base_url: profile.base_url ?? '', api_key: '', enabled: profile.enabled }); setMessage('')
  }
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault(); setError(''); setMessage('')
    try {
      if (editing === null) await createProviderProfile({ ...form, base_url: form.base_url || undefined, api_key: form.api_key || undefined })
      else await updateProviderProfile(editing, { provider: form.provider, model: form.model, base_url: form.base_url || undefined, enabled: form.enabled, api_key: form.api_key || undefined })
      setMessage('Provider profile saved. Credentials remain server-side.'); setEditing(null); setForm(initial); await refresh()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save provider') }
  }
  async function test(profile: ProviderProfile): Promise<void> {
    setTesting(profile.id); setError(''); setMessage('')
    try { const result = await testProviderProfile(profile.id); setMessage(`${profile.name}: ${result.message} (${result.latency_ms ?? '?'} ms)`) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Provider test failed') }
    finally { setTesting(null) }
  }

  const emptyProfile: WriterProfile = { name: '', pen_name: '', bio: '', default_format: 'feature', default_language: 'English', style_notes: '', preferences: {} }
  const [writerProfile, setWriterProfile] = useState<WriterProfile>(emptyProfile)
  const [profileSaved, setProfileSaved] = useState(false)
  const [memories, setMemories] = useState<WriterMemory[]>([])
  const [memoryDraft, setMemoryDraft] = useState({ kind: 'preference', text: '' })

  useEffect(() => {
    getWriterProfile().then(setWriterProfile).catch(() => undefined)
    listWriterMemories().then(setMemories).catch(() => undefined)
  }, [])

  async function saveProfile(event: FormEvent): Promise<void> {
    event.preventDefault()
    try {
      setWriterProfile(await saveWriterProfile(writerProfile))
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 3000)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save writer profile')
    }
  }

  async function remember(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!memoryDraft.text.trim()) return
    try {
      const memory = await addWriterMemory({ kind: memoryDraft.kind, text: memoryDraft.text.trim() })
      setMemories(current => [memory, ...current])
      setMemoryDraft(current => ({ ...current, text: '' }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save memory')
    }
  }

  async function forget(memoryId: number): Promise<void> {
    try { await forgetWriterMemory(memoryId); setMemories(current => current.filter(item => item.id !== memoryId)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to forget memory') }
  }

  return <div className="settings-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">✦</span><span className="wordmark"><em>Draft</em><b>Pilot</b></span></div><p className="eyebrow">Studio</p><nav><a href="/projects">Projects</a><a className="active" href="/settings">Settings</a></nav><div className="sidebar-note"><span className="status-dot" /> Local workspace</div></aside>
    <main className="main settings-main">
      <header className="topbar"><div><p className="eyebrow warm">CONFIGURATION</p><h1>Settings</h1></div><a className="button quiet" href="/projects">← Projects</a></header>
      <p className="settings-intro">Connect a model for your story team. API keys are encrypted by the server and never returned to this browser.</p>
      {error && <div className="notice">{error}<button onClick={() => setError('')}>×</button></div>}{message && <div className="success-notice">{message}</div>}
      <AppearancePanel />
      <div className="settings-grid">
        <section className="settings-card" aria-label="Default model server"><p className="eyebrow warm">DEFAULT MODEL SERVER</p><p className="helper">LM Studio (LLM__ settings). Tests and evals always run against local LM Studio.</p>{defaultModelsError && <p className="settings-error">{defaultModelsError}</p>}{defaultModels === null && !defaultModelsError && <p>Checking…</p>}{defaultModels && <ul className="model-list">{defaultModels.map(item => <li key={item.id} className={item.loaded ? 'loaded' : ''}><span>{item.id}</span><small>{item.kind}{item.loaded ? ' · loaded' : ''}</small></li>)}</ul>}</section>
        <section className="settings-card"><p className="eyebrow warm">{editing === null ? 'ADD PROVIDER' : 'EDIT PROVIDER'}</p><form onSubmit={event => void submit(event)}><label>Profile name<input required value={form.name} disabled={editing !== null} onChange={event => update('name', event.target.value)} placeholder="Studio Ollama" /></label><label>Provider<select value={form.provider} onChange={event => update('provider', event.target.value)}><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option><option value="gateway">OpenAI-compatible gateway</option><option value="ollama">Ollama</option><option value="lm_studio">LM Studio</option><option value="anthropic">Anthropic</option><option value="google">Google Gemini</option></select></label><label>Model <span className="helper">"auto" uses the first loaded LM Studio model</span><input required list="provider-models" value={form.model} onChange={event => update('model', event.target.value)} placeholder="Model identifier" /><datalist id="provider-models"><option value="auto" />{modelOptions.filter(item => item.kind !== 'embeddings').map(item => <option key={item.id} value={item.id}>{item.loaded ? 'loaded' : 'not loaded'}</option>)}</datalist></label><label>Base URL <span className="helper">Optional for provider defaults</span><input value={form.base_url} onChange={event => update('base_url', event.target.value)} placeholder="http://host.docker.internal:11434/v1" /></label><label>API key <span className="helper">Leave blank to keep the existing key</span><input type="password" autoComplete="new-password" value={form.api_key} onChange={event => update('api_key', event.target.value)} placeholder={editing !== null ? '••••••••' : 'Write-only credential'} /></label><label className="checkbox-label"><input type="checkbox" checked={form.enabled} onChange={event => update('enabled', event.target.checked)} /> Enabled</label><div><button className="button primary" type="submit">{editing === null ? 'Save provider' : 'Save changes'}</button>{editing !== null && <button className="button quiet" type="button" onClick={() => { setEditing(null); setForm(initial) }}>Cancel</button>}</div></form></section>
        <section><p className="eyebrow">SAVED PROFILES / {profiles.length}</p>{profiles.length === 0 && <div className="settings-empty">No provider profiles yet.</div>}{profiles.map(profile => <article className="provider-card" key={profile.id}><div><strong>{profile.name}</strong><p>{profile.provider} · {profile.model}</p><small>{profile.has_api_key ? 'Credential stored securely' : 'No API key configured'} · {profile.enabled ? 'Enabled' : 'Disabled'}</small></div><div className="provider-actions"><button className="mini-button" onClick={() => void test(profile)} disabled={testing === profile.id}>{testing === profile.id ? 'Testing…' : 'Test'}</button><button className="mini-button" onClick={() => void loadModels(profile)}>Models</button><button className="mini-button" onClick={() => edit(profile)}>Edit</button></div></article>)}</section>
      </div>
      <section className="settings-card writer-profile-card" aria-label="Writer Profile">
        <p className="eyebrow warm">WRITER PROFILE & PREFERENCES</p>
        <p className="helper">The writers' room reads this before every task: who you are, how you write, and what to avoid.</p>
        <form onSubmit={event => void saveProfile(event)}>
          <div className="two-up">
            <label>Full name
              <input
                aria-label="Writer full name"
                value={writerProfile.name}
                onChange={event => setWriterProfile(p => ({ ...p, name: event.target.value }))}
                placeholder="Your name"
              />
            </label>
            <label>Pen name / Alias
              <input
                aria-label="Writer pen name"
                value={writerProfile.pen_name}
                onChange={event => setWriterProfile(p => ({ ...p, pen_name: event.target.value }))}
                placeholder="Screenplay pseudonym"
              />
            </label>
            <label>Default screenplay format
              <select
                aria-label="Default screenplay format"
                value={writerProfile.default_format}
                onChange={event => setWriterProfile(p => ({ ...p, default_format: event.target.value }))}
              >
                <option value="feature">Feature film</option>
                <option value="pilot_hour">60-minute drama pilot</option>
                <option value="pilot_half_hour">30-minute comedy pilot</option>
                <option value="short">Short film</option>
              </select>
            </label>
            <label>Default writing language
              <input
                aria-label="Default writing language"
                value={writerProfile.default_language}
                onChange={event => setWriterProfile(p => ({ ...p, default_language: event.target.value }))}
                placeholder="English"
              />
            </label>
          </div>
          <label>Writer intent & bio
            <textarea
              aria-label="Writer intent & bio"
              value={writerProfile.bio}
              onChange={event => setWriterProfile(p => ({ ...p, bio: event.target.value }))}
              placeholder="Guiding themes, creative vision, or recurring genre interests…"
              rows={3}
            />
          </label>
          <label>Your style
            <textarea
              aria-label="Writer style notes"
              value={writerProfile.style_notes}
              onChange={event => setWriterProfile(p => ({ ...p, style_notes: event.target.value }))}
              placeholder="Voice, rhythm, dialogue habits, what you are going for — e.g. lean present-tense action, wry understatement, no speeches."
              rows={3}
            />
          </label>
          <div>
            <button className="button primary" type="submit">Save writer profile</button>
            {profileSaved && <span className="profile-saved-notice">Writer profile saved.</span>}
          </div>
        </form>
      </section>
      <section className="settings-card writer-memory-card" aria-label="Writer memories">
        <p className="eyebrow warm">WHAT THE ROOM REMEMBERS / {memories.length}</p>
        <form className="memory-form" onSubmit={event => void remember(event)}>
          <select aria-label="Memory kind" value={memoryDraft.kind} onChange={event => setMemoryDraft(current => ({ ...current, kind: event.target.value }))}>
            <option value="preference">Preference</option><option value="style">Style</option><option value="taboo">Never do</option><option value="fact">Fact</option>
          </select>
          <input aria-label="New memory" value={memoryDraft.text} onChange={event => setMemoryDraft(current => ({ ...current, text: event.target.value }))} placeholder="e.g. Never kill the dog." />
          <button className="button primary" type="submit">Remember</button>
        </form>
        {memories.length === 0 && <p className="settings-empty">Nothing yet. Add preferences the room should always respect.</p>}
        <ul className="memory-list">{memories.map(memory => <li key={memory.id}><span className={`memory-kind ${memory.kind}`}>{memory.kind}</span><span>{memory.text}</span><small>{memory.source}{memory.project_id ? ' · this project' : ''}</small><button className="mini-button" aria-label={`Forget ${memory.text}`} onClick={() => void forget(memory.id)}>Forget</button></li>)}</ul>
      </section>
    </main><aside className="settings-copilot"><CopilotPanel page="/settings" artifact="provider_settings" /></aside>
  </div>
}
