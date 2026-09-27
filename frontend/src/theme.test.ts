import { beforeEach, describe, expect, it } from 'vitest'
import { applyAppearance, DEFAULT_APPEARANCE, loadAppearance, normalizeAppearance, resolvedTheme, saveAppearance } from './theme'

describe('appearance', () => {
  beforeEach(() => { localStorage.clear(); document.documentElement.removeAttribute('data-theme') })

  it('keeps valid fields and replaces invalid ones with defaults', () => {
    expect(normalizeAppearance({ theme: 'night', accent: '#3f9e96' })).toEqual({ theme: 'night', accent: '#3f9e96' })
    expect(normalizeAppearance({ theme: 'neon', accent: 'red' })).toEqual(DEFAULT_APPEARANCE)
    expect(normalizeAppearance(null)).toEqual(DEFAULT_APPEARANCE)
    expect(normalizeAppearance({ theme: 'slate', accent: 'url(javascript:alert(1))' }).accent).toBe(DEFAULT_APPEARANCE.accent)
  })

  it('applies the theme and accent to the document', () => {
    applyAppearance({ theme: 'slate', accent: '#6d74d6' })
    expect(document.documentElement.dataset.theme).toBe('slate')
    expect(document.documentElement.style.getPropertyValue('--accent')).toBe('#6d74d6')
  })

  it('resolves system to paper or night', () => {
    expect(['paper', 'night']).toContain(resolvedTheme('system'))
    expect(resolvedTheme('night')).toBe('night')
  })

  it('persists across loads and survives corrupt storage', () => {
    saveAppearance({ theme: 'night', accent: '#d0617a' })
    expect(loadAppearance()).toEqual({ theme: 'night', accent: '#d0617a' })
    localStorage.setItem('draftpilot:appearance', '{not json')
    expect(loadAppearance()).toEqual(DEFAULT_APPEARANCE)
  })
})
