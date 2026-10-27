import { useEffect, useSyncExternalStore } from 'react'

/** What the writer is looking at, beyond the route: the dock sends it with every turn. */
export type ChatFocus = { artifact?: string | null; selection?: string | null; scene_id?: number | null }

let focus: ChatFocus = {}
const listeners = new Set<() => void>()

function setFocus(next: ChatFocus): void {
  focus = next
  listeners.forEach(listener => listener())
}

/** Read the current focus. */
export function useCurrentFocus(): ChatFocus {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, () => focus, () => focus)
}

/** Report a page's focus to the chat dock while the page is mounted. */
export function useChatFocus(artifact: string | null, selection: string | null = null, sceneId: number | null = null): void {
  useEffect(() => {
    setFocus({ artifact, selection, scene_id: sceneId })
    return () => setFocus({})
  }, [artifact, selection, sceneId])
}
