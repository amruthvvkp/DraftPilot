import { useEffect, useState } from 'react'

export default function EditorViewMode() {
  const [mode, setMode] = useState<'continuous' | 'paginated'>(() => document.documentElement.dataset.editorView === 'paginated' ? 'paginated' : 'continuous')

  useEffect(() => {
    document.documentElement.dataset.editorView = mode
    return () => { delete document.documentElement.dataset.editorView }
  }, [mode])

  return <section className="view-mode-panel" aria-label="Editor view mode"><div><p className="eyebrow warm">DOCUMENT VIEW</p><strong>{mode === 'continuous' ? 'Continuous canvas' : 'Paginated pages'}</strong><small>One semantic screenplay document, two reading views.</small></div><div className="view-mode-buttons"><button className={mode === 'continuous' ? 'mini-button selected' : 'mini-button'} onClick={() => setMode('continuous')}>Continuous</button><button className={mode === 'paginated' ? 'mini-button selected' : 'mini-button'} onClick={() => setMode('paginated')}>Paginated</button></div></section>
}
