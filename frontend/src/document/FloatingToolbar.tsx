import { type RefObject, useEffect, useState } from 'react'
import type { Editor } from '@tiptap/core'
import { AMBER } from './fountain'
import { ELEMENT_LABELS } from './schema'
import { currentElement } from './behaviour'

export const ELEMENT_OPTIONS = Object.entries(ELEMENT_LABELS)

/** Read the element type under the cursor ('heading' in a scene heading, '' elsewhere). */
export function cursorType(editor: Editor): string {
  const { $from } = editor.state.selection
  if ($from.parent.type.name === 'sceneHeading') return 'heading'
  return currentElement(editor.state) ? String($from.parent.attrs.element_type) : ''
}

/** Pick the element type under the cursor (the toolbar's *Aa*). */
export function ElementTypeSelect({ editor, label }: { editor: Editor; label: string }) {
  const type = cursorType(editor)
  return <select className="element-type-select" aria-label={label} value={type === 'heading' ? '' : type} disabled={!type || type === 'heading'}
    onChange={event => { editor.chain().focus().setElementType(event.target.value).run() }}>
    {type === 'heading' || !type ? <option value="">{type === 'heading' ? 'Scene heading' : '—'}</option> : null}
    {ELEMENT_OPTIONS.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
  </select>
}

/** The selection toolbar: undo/redo, element type, bold, italic, underline, strike, colour, dual dialogue. */
export default function FloatingToolbar({ editor, container }: { editor: Editor; container: RefObject<HTMLElement | null> }) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const [, setTick] = useState(0)

  useEffect(() => {
    const update = () => {
      setTick(tick => tick + 1)
      const { from, to, empty } = editor.state.selection
      const box = container.current?.getBoundingClientRect()
      if (empty || !box || !editor.isFocused) { setPosition(null); return }
      try {
        const start = editor.view.coordsAtPos(from)
        const end = editor.view.coordsAtPos(to)
        setPosition({ top: Math.min(start.top, end.top) - box.top - 46, left: Math.max(0, (start.left + end.left) / 2 - box.left - 170) })
      } catch { setPosition(null) }
    }
    const hide = () => setTimeout(() => { if (!editor.isFocused) setPosition(null) }, 150)
    editor.on('selectionUpdate', update)
    editor.on('transaction', update)
    editor.on('blur', hide)
    return () => { editor.off('selectionUpdate', update); editor.off('transaction', update); editor.off('blur', hide) }
  }, [editor, container])

  if (!position) return null
  const run = (command: (chain: ReturnType<Editor['chain']>) => ReturnType<Editor['chain']>) => () => { command(editor.chain().focus()).run() }
  const active = (name: string) => editor.isActive(name) ? 'true' : 'false'
  const dialogue = cursorType(editor) === 'dialogue'
  return <div className="floating-toolbar" role="toolbar" aria-label="Screenplay formatting toolbar" style={{ top: position.top, left: position.left }} onMouseDown={event => { if (!(event.target instanceof HTMLSelectElement)) event.preventDefault() }}>
    <button type="button" className="mini-button" aria-label="Undo" title="Undo (⌘Z)" disabled={!editor.can().undo()} onClick={run(chain => chain.undo())}>↶</button>
    <button type="button" className="mini-button" aria-label="Redo" title="Redo (⇧⌘Z)" disabled={!editor.can().redo()} onClick={run(chain => chain.redo())}>↷</button>
    <ElementTypeSelect editor={editor} label="Element type" />
    <button type="button" className="mini-button" aria-label="Bold text" aria-pressed={active('bold')} title="Bold (⌘B)" onClick={run(chain => chain.toggleBold())}><b>B</b></button>
    <button type="button" className="mini-button" aria-label="Italic text" aria-pressed={active('italic')} title="Italic (⌘I)" onClick={run(chain => chain.toggleItalic())}><i>I</i></button>
    <button type="button" className="mini-button" aria-label="Underline text" aria-pressed={active('underline')} title="Underline (⌘U)" onClick={run(chain => chain.toggleUnderline())}><u>U</u></button>
    <button type="button" className="mini-button" aria-label="Strike text" aria-pressed={active('strike')} title="Strike (⇧⌘S)" onClick={run(chain => chain.toggleStrike())}><s>S</s></button>
    <button type="button" className="mini-button color-action-btn" aria-label="Amber mark" aria-pressed={active('color')} title="Amber accent mark" onClick={run(chain => chain.toggleMark('color', { color: AMBER }))}><span className="color-swatch" /></button>
    {dialogue && <button type="button" className="mini-button" aria-label="Pair with previous dialogue" title="Dual dialogue" onClick={run(chain => chain.toggleDualDialogue())}>⫴</button>}
  </div>
}
