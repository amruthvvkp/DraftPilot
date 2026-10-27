import { useSyncExternalStore } from 'react'

export type EditorView = 'continuous' | 'paginated'
const listeners = new Set<() => void>()

function current(): EditorView {
  return document.documentElement.dataset.editorView === 'paginated' ? 'paginated' : 'continuous'
}

/** Switch the script between the continuous canvas and paginated pages (styles key off `html[data-editor-view]`). */
export function setEditorView(view: EditorView): void {
  document.documentElement.dataset.editorView = view
  listeners.forEach(listener => listener())
}

/** Read the current editor view; every control bound to it stays in sync. */
export function useEditorView(): [EditorView, (view: EditorView) => void] {
  const view = useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, current, () => 'continuous' as EditorView)
  return [view, setEditorView]
}
