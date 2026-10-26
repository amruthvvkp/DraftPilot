/** Sort rows by position, then id (the server's order). */
export function byPosition<T extends { position: number; id: number }>(rows: T[]): T[] {
  return [...rows].sort((a, b) => a.position - b.position || a.id - b.id)
}

/** Return a copy of `list` with the item at `from` moved to `to` (clamped). */
export function moveItem<T>(list: T[], from: number, to: number): T[] {
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(Math.max(0, Math.min(to, next.length)), 0, item)
  return next
}

/** Persist contiguous positions for `rows` in their current order, patching only rows that moved. */
export async function persistPositions<T extends { position: number }>(rows: T[], save: (row: T, position: number) => Promise<unknown>): Promise<void> {
  for (const [position, row] of rows.entries()) {
    if (row.position !== position) await save(row, position)
  }
}
