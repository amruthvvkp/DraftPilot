import { useEffect } from 'react'
import { useSearchParams } from 'react-router'

type TextFieldProps = {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  rows?: number
  hint?: string
  list?: string
  placeholder?: string
}

/** A labelled single-line input (rows = 1) or textarea, styled for the story pages. */
export function TextField({ id, label, value, onChange, rows = 1, hint, list, placeholder }: TextFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined
  return <div className="story-field">
    <label htmlFor={id}>{label}</label>
    {rows > 1
      ? <textarea id={id} rows={rows} value={value} placeholder={placeholder} aria-describedby={hintId} onChange={event => onChange(event.target.value)} />
      : <input id={id} value={value} list={list} placeholder={placeholder} aria-describedby={hintId} onChange={event => onChange(event.target.value)} />}
    {hint && <small id={hintId}>{hint}</small>}
  </div>
}

/** Focus the field named in `?field=` once the page is ready (Context map links use it). */
export function useFocusField(prefix: string, ready: boolean): void {
  const [params] = useSearchParams()
  const field = params.get('field')
  useEffect(() => {
    if (!ready || !field) return
    document.getElementById(`${prefix}-${field}`)?.focus()
  }, [prefix, field, ready])
}

/** Split a comma-separated list, dropping blanks. */
export function splitList(value: string): string[] {
  return value.split(',').map(item => item.trim()).filter(Boolean)
}

/** Save on Cmd/Ctrl+S. */
export function useSaveShortcut(save: () => void, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return
    const handle = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save() }
    }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [save, enabled])
}
