import type { KeyboardEvent } from 'react'
import type { ScreenplayBlock } from '../api'
import { normalizeTyped } from '../smartTyping'

export const ELEMENT_TYPES: [string, string][] = [
  ['action', 'Action'], ['character', 'Character'], ['dialogue', 'Dialogue'], ['parenthetical', 'Parenthetical'], ['transition', 'Transition'],
  ['lyric', 'Lyric'], ['note', 'Note'], ['section', 'Section'], ['synopsis', 'Synopsis'], ['shot', 'Shot'], ['page_break', 'Page break'],
]

/** Tab moves to the next script editor on the page. */
function advanceEditor(event: KeyboardEvent<HTMLTextAreaElement>): void {
  if (event.key !== 'Tab' || event.shiftKey) return
  event.preventDefault()
  const editors = Array.from(document.querySelectorAll<HTMLTextAreaElement>('.script-editor'))
  const next = editors[editors.indexOf(event.currentTarget) + 1]
  next?.focus()
}

type BlockRowProps = {
  block: ScreenplayBlock
  index: number
  count: number
  draft: string
  onDraft: (text: string) => void
  onFocus: () => void
  onBlur: () => void
  onTypeChange: (elementType: string) => void
  onMove: (delta: -1 | 1) => void
  onDelete: () => void
}

/** One screenplay element: its type (changed directly), its text, and move/delete controls. */
export default function BlockRow({ block, index, count, draft, onDraft, onFocus, onBlur, onTypeChange, onMove, onDelete }: BlockRowProps) {
  return <div className={block.is_dual ? 'semantic-row dual-block' : 'semantic-row'}>
    <select className="element-selector" value={block.element_type} onChange={event => onTypeChange(event.target.value)} aria-label={`Format ${block.element_type}`}>
      {ELEMENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select>
    {block.element_type === 'page_break'
      ? <div className="page-break-marker" role="separator" aria-label="Page break"><span>page break</span></div>
      : <textarea className={`script-editor ${block.element_type}`} data-block-id={block.id} onFocus={onFocus}
        list={block.element_type === 'character' ? 'screenplay-characters' : undefined} value={draft}
        onChange={event => onDraft(normalizeTyped(event.target.value, block.element_type))} onKeyDown={advanceEditor} onBlur={onBlur}
        aria-label={`Edit ${block.element_type}`} aria-keyshortcuts="Tab" />}
    <div className="block-actions" role="group" aria-label={`Block ${index + 1} actions`}>
      {block.origin && block.origin !== 'human' && <span className="block-origin" title="Last authored by">{block.origin.startsWith('proposal:') ? 'agent' : block.origin}</span>}
      <button type="button" className="mini-button" onClick={() => onMove(-1)} disabled={index === 0} aria-label={`Move block ${index + 1} up`}>↑</button>
      <button type="button" className="mini-button" onClick={() => onMove(1)} disabled={index === count - 1} aria-label={`Move block ${index + 1} down`}>↓</button>
      <button type="button" className="mini-button danger" onClick={onDelete} aria-label={`Delete block ${index + 1}`}>✕</button>
    </div>
  </div>
}
