/**
 * Inline Fountain markup ↔ marked text runs.
 *
 * Blocks keep their text as Fountain (`**bold**`, `*italic*`, `_underline_`, `~~strike~~` and the
 * amber `[[color:#hex]]…[[/color]]` mark), so the server, exports and agents never see editor marks.
 * The document editor parses that markup into marks and serialises the marks back when it saves.
 */

export type MarkName = 'bold' | 'italic' | 'underline' | 'strike' | 'color'
export type RunMark = { type: MarkName; attrs?: { color: string } }
export type Run = { text: string; marks: RunMark[] }

/** Marks open in this order and close in reverse, so `***x***` round-trips. */
const ORDER: MarkName[] = ['color', 'bold', 'italic', 'underline', 'strike']
const DELIMITERS: [string, Exclude<MarkName, 'color'>][] = [['**', 'bold'], ['~~', 'strike'], ['*', 'italic'], ['_', 'underline']]
const COLOR_OPEN = /^\[\[color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\]\]/
const COLOR_CLOSE = '[[/color]]'
const ESCAPABLE = new Set(['*', '_', '~', '\\', '['])
export const AMBER = '#dda05d'

function markKey(mark: RunMark): string {
  return mark.type === 'color' ? `color:${mark.attrs?.color ?? ''}` : mark.type
}

function sameMarks(a: RunMark[], b: RunMark[]): boolean {
  return a.length === b.length && a.every((mark, index) => markKey(mark) === markKey(b[index]))
}

function sorted(marks: RunMark[]): RunMark[] {
  return [...marks].sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type))
}

/** Find the next unescaped `delimiter` at or after `from` (a single `*` never matches inside `**`). */
function findClosing(text: string, delimiter: string, from: number): number {
  for (let index = from; index < text.length; index += 1) {
    if (text[index] === '\\') { index += 1; continue }
    if (!text.startsWith(delimiter, index)) continue
    if (delimiter === '*' && text.startsWith('**', index)) { index += 1; continue }
    return index
  }
  return -1
}

/** Parse inline Fountain markup into runs of text with marks. */
export function parseInline(text: string): Run[] {
  const runs: Run[] = []
  const active: RunMark[] = []
  const colors: string[] = []
  let buffer = ''
  const flush = () => {
    if (!buffer) return
    const marks = sorted([...active, ...(colors.length ? [{ type: 'color' as const, attrs: { color: colors[colors.length - 1] } }] : [])])
    const last = runs[runs.length - 1]
    if (last && sameMarks(last.marks, marks)) last.text += buffer
    else runs.push({ text: buffer, marks })
    buffer = ''
  }
  let index = 0
  while (index < text.length) {
    const char = text[index]
    if (char === '\\' && index + 1 < text.length && ESCAPABLE.has(text[index + 1])) { buffer += text[index + 1]; index += 2; continue }
    const color = COLOR_OPEN.exec(text.slice(index))
    if (color && text.indexOf(COLOR_CLOSE, index + color[0].length) !== -1) { flush(); colors.push(color[1]); index += color[0].length; continue }
    if (text.startsWith(COLOR_CLOSE, index) && colors.length) { flush(); colors.pop(); index += COLOR_CLOSE.length; continue }
    const delimiter = DELIMITERS.find(([token]) => text.startsWith(token, index))
    if (delimiter) {
      const [token, type] = delimiter
      const open = active.findIndex(mark => mark.type === type)
      if (open !== -1) { flush(); active.splice(open, 1); index += token.length; continue }
      if (findClosing(text, token, index + token.length) > index + token.length) { flush(); active.push({ type }); index += token.length; continue }
    }
    buffer += char
    index += 1
  }
  flush()
  return runs
}

function opener(mark: RunMark): string {
  return mark.type === 'color' ? `[[color:${mark.attrs?.color ?? AMBER}]]` : DELIMITERS.find(([, type]) => type === mark.type)![0]
}

function closer(mark: RunMark): string {
  return mark.type === 'color' ? COLOR_CLOSE : opener(mark)
}

function escapeLiteral(text: string): string {
  return text.replace(/[\\*_~]|\[\[/g, match => `\\${match}`)
}

function emit(runs: Run[], escape: boolean): string {
  let out = ''
  let open: RunMark[] = []
  for (const run of runs) {
    if (!run.text) continue
    const wanted = sorted(run.marks)
    // Close back to the longest shared prefix, then open what is new.
    let keep = 0
    while (keep < open.length && keep < wanted.length && markKey(open[keep]) === markKey(wanted[keep])) keep += 1
    for (let index = open.length - 1; index >= keep; index -= 1) out += closer(open[index])
    for (let index = keep; index < wanted.length; index += 1) out += opener(wanted[index])
    open = wanted
    out += escape ? escapeLiteral(run.text) : run.text
  }
  for (let index = open.length - 1; index >= 0; index -= 1) out += closer(open[index])
  return out
}

/** Merge adjacent runs with the same marks, so two spellings of one formatted text compare equal. */
export function normalizeRuns(runs: Run[]): Run[] {
  const out: Run[] = []
  for (const run of runs) {
    if (!run.text) continue
    const marks = sorted(run.marks)
    const last = out[out.length - 1]
    if (last && sameMarks(last.marks, marks)) last.text += run.text
    else out.push({ text: run.text, marks })
  }
  return out
}

/** True when two run lists hold the same text with the same marks. */
export function sameRuns(a: Run[], b: Run[]): boolean {
  const key = (runs: Run[]) => JSON.stringify(normalizeRuns(runs).map(run => [run.text, run.marks.map(markKey)]))
  return key(a) === key(b)
}

/** Serialise runs back to Fountain, escaping literal markup only when it would otherwise read as a mark. */
export function serializeInline(runs: Run[]): string {
  const plain = emit(runs, false)
  return sameRuns(parseInline(plain), runs) ? plain : emit(runs, true)
}
