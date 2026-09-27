import { useEffect, useRef, useState } from 'react'
import { getWriterProfile, saveWriterProfile } from './api'
import { ACCENTS, Appearance, loadAppearance, normalizeAppearance, saveAppearance, THEMES } from './theme'

/** Pick the studio theme and accent; applies instantly and follows the writer to other browsers. */
export default function AppearancePanel() {
  const [appearance, setAppearance] = useState<Appearance>(loadAppearance)
  const [synced, setSynced] = useState<'idle' | 'saved' | 'local'>('idle')

  useEffect(() => {
    getWriterProfile().then(profile => {
      const stored = profile.preferences?.appearance
      if (stored) { const next = normalizeAppearance(stored); latest.current = next; setAppearance(next); saveAppearance(next) }
    }).catch(() => undefined)
  }, [])

  const latest = useRef(appearance)
  const queue = useRef<Promise<void>>(Promise.resolve())

  function choose(change: Partial<Appearance>): void {
    const next = normalizeAppearance({ ...latest.current, ...change })
    latest.current = next
    setAppearance(next)
    saveAppearance(next)
    // Saves run one at a time and always send the newest choice, so quick clicks cannot land out of order.
    queue.current = queue.current.then(async () => {
      if (latest.current !== next) return
      try {
        const profile = await getWriterProfile()
        await saveWriterProfile({ ...profile, preferences: { ...profile.preferences, appearance: next } })
        setSynced('saved')
      } catch { setSynced('local') }
    })
  }

  return <section className="settings-card appearance-card" aria-label="Appearance">
    <p className="eyebrow warm">APPEARANCE</p>
    <p className="helper">Choose how the studio looks. It applies immediately and follows you to other browsers.</p>
    <div className="theme-options" role="radiogroup" aria-label="Theme">{THEMES.map(theme => <button key={theme.key} type="button" role="radio" aria-checked={appearance.theme === theme.key} className={appearance.theme === theme.key ? 'chosen' : ''} onClick={() => choose({ theme: theme.key })}><span className="theme-swatch" style={{ background: `linear-gradient(135deg, ${theme.swatch[0]} 50%, ${theme.swatch[1]} 50%)` }} />{theme.label}</button>)}</div>
    <div className="accent-options" role="radiogroup" aria-label="Accent colour">{ACCENTS.map(accent => <button key={accent.value} type="button" role="radio" aria-checked={appearance.accent === accent.value} aria-label={accent.label} title={accent.label} className={appearance.accent === accent.value ? 'chosen' : ''} style={{ background: accent.value }} onClick={() => choose({ accent: accent.value })} />)}<label className="custom-accent">Custom<input type="color" aria-label="Custom accent colour" value={appearance.accent} onChange={event => choose({ accent: event.target.value })} /></label></div>
    {synced === 'saved' && <small className="settings-success">Saved to your writer profile.</small>}
    {synced === 'local' && <small className="helper">Saved in this browser only.</small>}
  </section>
}
