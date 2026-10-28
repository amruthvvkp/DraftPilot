/** Which script editor a writer uses: the per-block Classic editor or the single Document editor. */
import { useSyncExternalStore } from 'react'

export type EditorMode = 'classic' | 'document'
export const EDITOR_MODES: { key: EditorMode; label: string; description: string }[] = [
  { key: 'classic', label: 'Classic', description: 'One box per element, one scene at a time.' },
  { key: 'document', label: 'Document', description: 'The whole draft as one page, with the outline inline.' },
]
export const DEFAULT_EDITOR_MODE: EditorMode = 'classic'
const STORAGE_KEY = 'draftpilot:editor'
const listeners = new Set<() => void>()

/** Return a valid editor mode, or the default. */
export function normalizeEditorMode(value: unknown): EditorMode {
  return value === 'document' || value === 'classic' ? value : DEFAULT_EDITOR_MODE
}

/** Return the editor mode saved in this browser. */
export function loadEditorMode(): EditorMode {
  try { return normalizeEditorMode(localStorage.getItem(STORAGE_KEY)) } catch { return DEFAULT_EDITOR_MODE }
}

/** Save the editor mode in this browser and tell every open view. */
export function saveEditorMode(mode: EditorMode): void {
  try { localStorage.setItem(STORAGE_KEY, mode) } catch { /* private mode: keep it for this tab */ }
  listeners.forEach(listener => listener())
}

/** Read the editor mode; components re-render when it changes. */
export function useEditorMode(): EditorMode {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, loadEditorMode, () => DEFAULT_EDITOR_MODE)
}
