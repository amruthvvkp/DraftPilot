export const DOCK_KEY = 'draftpilot:chat-dock'

/** Whether the chat dock starts open: on wide screens by default; the writer's own choice wins once made. */
export function readDockOpen(): boolean {
  let saved: string | null = null
  try { saved = window.localStorage.getItem(DOCK_KEY) } catch { /* private mode */ }
  return saved ? saved === 'open' : window.innerWidth >= 1440
}
