import { useEffect, useState } from 'react'
import { getWriterProfile, saveWriterProfile } from './api'
import { EDITOR_MODES, type EditorMode, normalizeEditorMode, saveEditorMode, useEditorMode } from './editorMode'

/** Choose the script editor; saved in this browser and in the writer profile. */
export default function EditorPanel() {
  const mode = useEditorMode()
  const [synced, setSynced] = useState<'idle' | 'saved' | 'local'>('idle')

  useEffect(() => {
    getWriterProfile().then(profile => {
      const stored = profile.preferences?.editor
      if (stored) saveEditorMode(normalizeEditorMode(stored))
    }).catch(() => undefined)
  }, [])

  async function choose(next: EditorMode): Promise<void> {
    saveEditorMode(next)
    try {
      const profile = await getWriterProfile()
      await saveWriterProfile({ ...profile, preferences: { ...profile.preferences, editor: next } })
      setSynced('saved')
    } catch { setSynced('local') }
  }

  return <section className="settings-card editor-mode-card" aria-label="Editor">
    <p className="eyebrow warm">EDITOR</p>
    <p className="helper">Choose how you write the script. You can switch at any time; both editors save to the same draft.</p>
    <div className="theme-options" role="radiogroup" aria-label="Script editor">
      {EDITOR_MODES.map(item => <button key={item.key} type="button" role="radio" aria-checked={mode === item.key} className={mode === item.key ? 'chosen' : ''} title={item.description} onClick={() => void choose(item.key)}>{item.label}</button>)}
    </div>
    <small className="helper">{EDITOR_MODES.find(item => item.key === mode)?.description}</small>
    {synced === 'saved' && <small className="settings-success">Saved to your writer profile.</small>}
    {synced === 'local' && <small className="helper">Saved in this browser only.</small>}
  </section>
}
