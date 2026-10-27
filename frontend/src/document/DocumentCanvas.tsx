import './document.css'
import { memo, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { EditorContent, ReactNodeViewRenderer, useEditor, type UseEditorOptions } from '@tiptap/react'
import type { Editor } from '@tiptap/core'
import { Placeholder } from '@tiptap/extensions'
import { approveAgentProposal, createProjectScene, getAgentProposals, type ProjectWorkspace, rejectAgentProposal, rollbackAgentProposal, writeSceneContent } from '../api'
import { errorMessage, keys, useBeats } from '../data/queries'
import { storyApi } from '../storyApi'
import { REMOTE, ScriptBehaviour } from './behaviour'
import BeatNoteView, { type BeatActions } from './BeatNoteView'
import { buildDoc, sceneNodes } from './convert'
import FloatingToolbar, { ElementTypeSelect } from './FloatingToolbar'
import { type OverlayActions, overlayKey, ScriptOverlay } from './overlay'
import { BeatNote, ELEMENT_LABELS, schemaExtensions } from './schema'
import { dispatchRemote, DocumentSync, flushPendingDOM, type SyncStatus } from './sync'

export type DocumentFocus = { sceneId: number | null; selection: string | null; blockIds: number[] }
export type Jump = { sceneId: number; nonce: number }

type Props = {
  projectId: number
  workspace: ProjectWorkspace
  onFocusChange: (focus: DocumentFocus) => void
  jump: Jump | null
  onStatus?: (status: SyncStatus) => void
}

const STATUS_TEXT: Record<SyncStatus, string> = { saved: 'All changes saved', unsaved: 'Unsaved changes', saving: 'Saving…', error: 'Not saved' }

/** Describe the selection for the chat: the selected text and the blocks it touches. */
function describeFocus(editor: Editor): DocumentFocus {
  const { from, to, empty, $from } = editor.state.selection
  let sceneId: number | null = null
  for (let depth = $from.depth; depth > 0; depth -= 1) if ($from.node(depth).type.name === 'scene') sceneId = Number($from.node(depth).attrs.scene_id)
  if (empty) return { sceneId, selection: null, blockIds: [] }
  const blockIds: number[] = []
  editor.state.doc.nodesBetween(from, to, node => {
    if (node.type.name === 'element') { if (node.attrs.block_id) blockIds.push(Number(node.attrs.block_id)); return false }
    return true
  })
  const text = editor.state.doc.textBetween(from, to, '\n').trim()
  const quoted = text.length > 600 ? `${text.slice(0, 600)}…` : text
  return { sceneId, selection: `"${quoted}"${blockIds.length ? ` (blocks ${blockIds.join(', ')})` : ''}`, blockIds }
}

/** The title page as a card at the top of the draft. */
function TitlePageCard({ workspace }: { workspace: ProjectWorkspace }) {
  const page = workspace.screenplay?.title_page ?? {}
  const title = page.Title || workspace.screenplay?.title || workspace.project.title
  const rest = Object.entries(page).filter(([key, value]) => key !== 'Title' && value)
  return <section className="title-page-card" aria-label="Title page">
    <p className="eyebrow warm">TITLE PAGE</p>
    <h2>{title}</h2>
    {rest.length ? <dl>{rest.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      : <p className="helper">Import a Fountain or FDX title page to fill this in.</p>}
  </section>
}

/**
 * Own the TipTap editor in a component that only renders when its (stable) options change: TipTap
 * re-applies its state to the view after every render of the component that calls `useEditor`,
 * which would race the writer's keystrokes if the canvas around it re-rendered while typing.
 */
const EditorHost = memo(function EditorHost({ options, onReady }: { options: UseEditorOptions; onReady: (editor: Editor | null) => void }) {
  const editor = useEditor(options, [options])
  // Hand the editor up only once its view is mounted; until then `editor.view` throws.
  useEffect(() => {
    if (!editor) return
    const ready = () => onReady(editor)
    if (editor.isInitialized) ready()
    else editor.on('create', ready)
    return () => { editor.off('create', ready); onReady(null) }
  }, [editor, onReady])
  return <EditorContent editor={editor} />
})

/** The single-document script editor: the whole draft as one page, with acts and beats inline. */
export default function DocumentCanvas({ projectId, workspace, onFocusChange, jump, onStatus }: Props) {
  const queryClient = useQueryClient()
  const { data: beats, isFetched: beatsFetched } = useBeats(projectId)
  const { data: proposals } = useQuery({ queryKey: keys.proposals(projectId), queryFn: () => getAgentProposals(projectId) })
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [outlineHidden, setOutlineHidden] = useState(() => localStorage.getItem('draftpilot:outline-hidden') === 'true')
  const [error, setError] = useState('')
  const container = useRef<HTMLDivElement>(null)
  const latest = useRef({ workspace, beats: beats ?? [] })
  latest.current = { workspace, beats: beats ?? [] }
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) }) }

  const sync = useMemo(() => {
    const controller = new DocumentSync({
      write: (sceneId, version, content) => writeSceneContent(projectId, sceneId, version, content),
      refresh,
    })
    controller.init(workspace, beats ?? [])
    return controller
    // One controller per draft; the parent remounts this component when the draft changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])
  const syncState = useSyncExternalStore(sync.subscribe, sync.getSnapshot)

  const overlayActions = useRef<OverlayActions>({
    accept: () => undefined, reject: () => undefined, rollback: () => undefined,
    keepMine: id => sync.keepMine(id), loadTheirs: id => sync.loadTheirs(id),
    toggleAct: id => setCollapsed(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }),
  })
  const beatActions = useRef<BeatActions>({ saveBeat: async () => false, createScene: async () => undefined })

  const focusChange = useRef(onFocusChange)
  focusChange.current = onFocusChange
  // Stable options: the editor is created once per draft, and its host never re-renders while typing.
  const options = useMemo<UseEditorOptions>(() => ({
    extensions: [
      ...schemaExtensions().filter(extension => extension.name !== 'beatNote'),
      BeatNote.extend({
        addOptions() { return { beatActions } },
        addNodeView() { return ReactNodeViewRenderer(BeatNoteView) },
      }),
      ScriptBehaviour.configure({ owner: blockId => sync.owners.get(blockId) }),
      ScriptOverlay.configure({ actions: overlayActions }),
      Placeholder.configure({ placeholder: ({ node }) => node.type.name === 'sceneHeading' ? 'INT. LOCATION - DAY' : ELEMENT_LABELS[String(node.attrs.element_type)] ?? '' }),
    ],
    content: buildDoc(latest.current.workspace, latest.current.beats),
    enableInputRules: false,
    enablePasteRules: false,
    editorProps: { attributes: { class: 'script-document', role: 'textbox', 'aria-multiline': 'true', 'aria-label': 'Screenplay', spellcheck: 'true' } },
    onTransaction: ({ editor: current, transaction }) => {
      if (transaction.docChanged && !transaction.getMeta(REMOTE)) sync.noteChange(transaction.before, current.state.doc)
    },
    onSelectionUpdate: ({ editor: current }) => focusChange.current(describeFocus(current)),
  }), [sync])
  const [editor, setEditor] = useState<Editor | null>(null)

  useEffect(() => {
    if (!editor) return
    sync.attach(editor)
    const flush = () => { void sync.flush() }
    window.addEventListener('pagehide', flush)
    return () => { window.removeEventListener('pagehide', flush); void sync.detach(editor) }
  }, [editor, sync])

  // Live sync: every refetch of the workspace or the beats is folded into the document.
  useEffect(() => { if (editor && beatsFetched) sync.reconcile(workspace, beats ?? []) }, [editor, sync, workspace, beats, beatsFetched])
  useEffect(() => { onStatus?.(syncState.status) }, [onStatus, syncState.status])

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    flushPendingDOM(editor)
    dispatchRemote(editor, editor.state.tr.setMeta(overlayKey, { proposals: proposals ?? [], conflicts: syncState.conflicts, collapsed, busy: syncState.busy }))
  }, [editor, proposals, syncState.conflicts, syncState.busy, collapsed])

  // The navigator jumps to a scene: put the cursor at the end of its heading.
  useEffect(() => {
    if (!editor || !jump) return
    const entry = sceneNodes(editor.state.doc).get(jump.sceneId)
    if (!entry) return
    const at = entry.pos + 2 + entry.node.child(0).content.size
    editor.chain().focus().setTextSelection(at).scrollIntoView().run()
    editor.view.dom.querySelector(`[data-scene-id="${jump.sceneId}"]`)?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [editor, jump])

  useEffect(() => { localStorage.setItem('draftpilot:outline-hidden', String(outlineHidden)) }, [outlineHidden])

  async function settle(change: () => Promise<unknown>, fallback: string): Promise<void> {
    setError('')
    try { await change() } catch (reason) { setError(errorMessage(reason, fallback)) }
    void queryClient.invalidateQueries({ queryKey: keys.proposals(projectId) })
    refresh()
  }
  overlayActions.current.accept = id => void settle(() => approveAgentProposal(projectId, id), 'Unable to accept the proposal')
  overlayActions.current.reject = id => void settle(() => rejectAgentProposal(projectId, id), 'Unable to reject the proposal')
  overlayActions.current.rollback = id => void settle(() => rollbackAgentProposal(projectId, id), 'Unable to roll back the proposal')
  beatActions.current.saveBeat = async (beatId, fields) => {
    const row = latest.current.beats.find(beat => beat.id === beatId)
    if (!row) return false
    try {
      await storyApi.updateBeat(projectId, row, fields)
      void queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
      return true
    } catch (reason) {
      setError(errorMessage(reason, 'Unable to save the beat'))
      void queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
      return false
    }
  }
  beatActions.current.createScene = async beatId => {
    const row = latest.current.beats.find(beat => beat.id === beatId)
    const screenplayId = latest.current.workspace.screenplay?.id
    if (!row || !screenplayId || !editor) return
    // The new scene goes where the placeholder sits: after the scenes above it in its act.
    let actId = row.act_id ?? latest.current.workspace.acts[0]?.id
    let position = 0
    editor.state.doc.forEach(act => {
      let before = 0
      act.forEach(child => {
        if (child.type.name === 'scene') before += 1
        if (child.type.name === 'beatNote' && child.attrs.beat_id === beatId) { actId = Number(act.attrs.act_id); position = before }
      })
    })
    if (!actId) return
    await settle(async () => {
      const scene = await createProjectScene(projectId, screenplayId, actId!, row.title.toUpperCase() || 'INT. - DAY', position)
      await storyApi.updateBeat(projectId, row, { scene_ids: [...row.scene_ids, scene.id] })
      void queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
    }, 'Unable to create a scene from the beat')
  }

  return <div className={`document-canvas${outlineHidden ? ' outline-hidden' : ''}`} ref={container}>
    <div className="document-toolbar" role="toolbar" aria-label="Document tools">
      {editor && <ElementTypeSelect editor={editor} label="Current element type" />}
      <button type="button" className="view-switch" role="switch" aria-checked={!outlineHidden} onClick={() => setOutlineHidden(value => !value)}>
        Outline <i className={outlineHidden ? 'toggle' : 'toggle on'} aria-hidden="true" />
      </button>
      <span className={`sync-state ${syncState.status}`} role="status" aria-label="Save status">{STATUS_TEXT[syncState.status]}{syncState.error ? `: ${syncState.error}` : ''}</span>
    </div>
    {error && <div className="notice" role="alert">{error}<button type="button" onClick={() => setError('')} aria-label="Dismiss">×</button></div>}
    <article className="script-page document-page">
      <TitlePageCard workspace={workspace} />
      <EditorHost options={options} onReady={setEditor} />
    </article>
    {editor && <FloatingToolbar editor={editor} container={container} />}
  </div>
}

