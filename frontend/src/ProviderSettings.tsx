import { type FormEvent, useEffect, useState } from 'react'
import { createProviderProfile, listProviderProfiles, ProviderProfile, testProviderProfile, updateProviderProfile } from './api'
import './provider-settings.css'

const initial = { name: '', provider: 'ollama', model: 'llama3.2', base_url: '', api_key: '', enabled: true }

export default function ProviderSettings() {
  const [profiles, setProfiles] = useState<ProviderProfile[]>([])
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState<number | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try { setProfiles(await listProviderProfiles()) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load providers') }
  }
  useEffect(() => { void refresh() }, [])
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

  return <div className="settings-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">✦</span><span className="wordmark"><em>Draft</em><b>Pilot</b></span></div><p className="eyebrow">Studio</p><nav><a href="/projects">Projects</a><a className="active" href="/settings">Settings</a></nav><div className="sidebar-note"><span className="status-dot" /> Local workspace</div></aside>
    <main className="main settings-main">
      <header className="topbar"><div><p className="eyebrow warm">CONFIGURATION</p><h1>Provider settings</h1></div><a className="button quiet" href="/projects">← Projects</a></header>
      <p className="settings-intro">Connect a model for your story team. API keys are encrypted by the server and never returned to this browser.</p>
      {error && <div className="notice">{error}<button onClick={() => setError('')}>×</button></div>}{message && <div className="success-notice">{message}</div>}
      <div className="settings-grid">
        <section className="settings-card"><p className="eyebrow warm">{editing === null ? 'ADD PROVIDER' : 'EDIT PROVIDER'}</p><form onSubmit={event => void submit(event)}><label>Profile name<input required value={form.name} disabled={editing !== null} onChange={event => update('name', event.target.value)} placeholder="Studio Ollama" /></label><label>Provider<select value={form.provider} onChange={event => update('provider', event.target.value)}><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option><option value="gateway">OpenAI-compatible gateway</option><option value="ollama">Ollama</option><option value="lm_studio">LM Studio</option></select></label><label>Model<input required value={form.model} onChange={event => update('model', event.target.value)} placeholder="Model identifier" /></label><label>Base URL <span className="helper">Optional for provider defaults</span><input value={form.base_url} onChange={event => update('base_url', event.target.value)} placeholder="http://host.docker.internal:11434/v1" /></label><label>API key <span className="helper">Leave blank to keep the existing key</span><input type="password" autoComplete="new-password" value={form.api_key} onChange={event => update('api_key', event.target.value)} placeholder={editing !== null ? '••••••••' : 'Write-only credential'} /></label><label className="checkbox-label"><input type="checkbox" checked={form.enabled} onChange={event => update('enabled', event.target.checked)} /> Enabled</label><div><button className="button primary" type="submit">{editing === null ? 'Save provider' : 'Save changes'}</button>{editing !== null && <button className="button quiet" type="button" onClick={() => { setEditing(null); setForm(initial) }}>Cancel</button>}</div></form></section>
        <section><p className="eyebrow">SAVED PROFILES / {profiles.length}</p>{profiles.length === 0 && <div className="settings-empty">No provider profiles yet.</div>}{profiles.map(profile => <article className="provider-card" key={profile.id}><div><strong>{profile.name}</strong><p>{profile.provider} · {profile.model}</p><small>{profile.has_api_key ? 'Credential stored securely' : 'No API key configured'} · {profile.enabled ? 'Enabled' : 'Disabled'}</small></div><div className="provider-actions"><button className="mini-button" onClick={() => void test(profile)} disabled={testing === profile.id}>{testing === profile.id ? 'Testing…' : 'Test'}</button><button className="mini-button" onClick={() => edit(profile)}>Edit</button></div></article>)}</section>
      </div>
    </main>
  </div>
}
