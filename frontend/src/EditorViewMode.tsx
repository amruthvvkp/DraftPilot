import { useEditorView } from './script/editorView'

/** Choose between the continuous canvas and paginated pages. */
export default function EditorViewMode() {
  const [mode, setMode] = useEditorView()
  return <section className="view-mode-panel" aria-label="Editor view mode">
    <div>
      <p className="eyebrow warm">DOCUMENT VIEW</p>
      <strong>{mode === 'continuous' ? 'Continuous canvas' : 'Paginated pages'}</strong>
      <small>One semantic screenplay document, two reading views.</small>
    </div>
    <div className="view-mode-buttons">
      <button className={mode === 'continuous' ? 'mini-button selected' : 'mini-button'} onClick={() => setMode('continuous')}>Continuous</button>
      <button className={mode === 'paginated' ? 'mini-button selected' : 'mini-button'} onClick={() => setMode('paginated')}>Paginated</button>
    </div>
  </section>
}
