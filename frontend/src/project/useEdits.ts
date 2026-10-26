import { useCallback, useState } from 'react'

export type Edits<F extends string> = {
  value: (name: F) => string
  set: (name: F, value: string) => void
  changed: Partial<Record<F, string>>
  dirty: boolean
  reset: () => void
}

/**
 * Track local edits over a server row. Untouched fields always show the latest server value, so live
 * updates from other sessions flow in; touched fields keep the writer's text until saved or discarded.
 */
export function useEdits<F extends string>(server: Partial<Record<F, unknown>> | undefined): Edits<F> {
  const [edits, setEdits] = useState<Partial<Record<F, string>>>({})
  const serverValue = (name: F): string => {
    const raw = server?.[name]
    if (Array.isArray(raw)) return raw.join(', ')
    return raw === null || raw === undefined ? '' : String(raw)
  }
  const changed = Object.fromEntries(
    (Object.entries(edits) as [F, string][]).filter(([name, text]) => text !== serverValue(name)),
  ) as Partial<Record<F, string>>
  const reset = useCallback(() => setEdits({}), [])
  return {
    value: name => edits[name] ?? serverValue(name),
    set: (name, text) => setEdits(current => ({ ...current, [name]: text })),
    changed,
    dirty: Object.keys(changed).length > 0,
    reset,
  }
}
