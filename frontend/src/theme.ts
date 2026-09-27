/** Studio appearance: a theme (paper, slate, night, or follow the system) plus an accent colour. */

export type ThemeName = 'system' | 'paper' | 'slate' | 'night'
export type Appearance = { theme: ThemeName; accent: string }

export const THEMES: { key: ThemeName; label: string; swatch: [string, string] }[] = [
  { key: 'system', label: 'System', swatch: ['#fffdf9', '#221f1b'] },
  { key: 'paper', label: 'Paper', swatch: ['#fffdf9', '#403b35'] },
  { key: 'slate', label: 'Slate', swatch: ['#fbfcfd', '#2c323a'] },
  { key: 'night', label: 'Night', swatch: ['#221f1b', '#ede7dc'] },
]

export const ACCENTS: { label: string; value: string }[] = [
  { label: 'Amber', value: '#d69a55' },
  { label: 'Teal', value: '#3f9e96' },
  { label: 'Rose', value: '#d0617a' },
  { label: 'Indigo', value: '#6d74d6' },
  { label: 'Sage', value: '#7fa06a' },
]

export const DEFAULT_APPEARANCE: Appearance = { theme: 'system', accent: ACCENTS[0].value }
const STORAGE_KEY = 'draftpilot:appearance'
const HEX = /^#[0-9a-f]{6}$/i

/** Return a valid appearance, falling back field by field to the defaults. */
export function normalizeAppearance(value: unknown): Appearance {
  const candidate = (value && typeof value === 'object' ? value : {}) as Partial<Appearance>
  const theme = THEMES.some(item => item.key === candidate.theme) ? candidate.theme as ThemeName : DEFAULT_APPEARANCE.theme
  const accent = typeof candidate.accent === 'string' && HEX.test(candidate.accent) ? candidate.accent : DEFAULT_APPEARANCE.accent
  return { theme, accent }
}

/** Resolve "system" to the concrete theme the OS prefers. */
export function resolvedTheme(theme: ThemeName): Exclude<ThemeName, 'system'> {
  if (theme !== 'system') return theme
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'night' : 'paper'
}

/** Apply an appearance to the document. */
export function applyAppearance(appearance: Appearance): void {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme(appearance.theme)
  root.style.setProperty('--accent', appearance.accent)
}

/** Return the appearance saved in this browser. */
export function loadAppearance(): Appearance {
  try { return normalizeAppearance(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')) } catch { return DEFAULT_APPEARANCE }
}

/** Save and apply an appearance in this browser. */
export function saveAppearance(appearance: Appearance): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(appearance))
  applyAppearance(appearance)
}

/** Apply the saved appearance now and keep "system" in step with the OS. */
export function initAppearance(): void {
  applyAppearance(loadAppearance())
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => applyAppearance(loadAppearance()))
}
