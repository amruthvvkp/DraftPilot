import './room.css'
import { type ChangeEvent, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { CLIENT_ID, createProjectBackup, deleteProjectBlock, getDialogueTranslations, importScreenplay, listProjectBackups, ProjectBackup, ProjectWorkspace, reorderProjectBlocks, restoreProjectBackup, saveDialogueTranslation, Scene, ScreenplayBlock, subscribeProjectEvents, updateProject, updateProjectBlock, updateProjectScene } from './api'
import { errorMessage, keys, useWorkspace } from './data/queries'
import { storyApi } from './storyApi'
import Timeline from './Timeline'
import { useChatFocus } from './chat/focus'
import McpApprovals from './McpApprovals'
import RevisionPanel from './RevisionPanel'
import BlockCreationPanel from './BlockCreationPanel'
import SceneCreationPanel from './SceneCreationPanel'
import ConfirmDialog from './project/ConfirmDialog'
import BlockRow from './script/BlockRow'
import { useEditorView } from './script/editorView'
import SceneNavigator, { type SceneMoves, type Timing } from './script/SceneNavigator'
import { inferElement } from './smartTyping'
import './backup.css'

type WorkspaceProps = { projectId: number; initialTimeline?: boolean }

function estimateDuration(body: string): number {
  return Math.max(30, Math.round(body.split(/\s+/).filter(Boolean).length / 2))
}

/** Scene timings from the server, or a word-count estimate when it sent none. */
function sceneTimings(workspace: ProjectWorkspace | undefined): { timings: Map<number, Timing>; total: number } {
  const timings = new Map<number, Timing>()
  if (workspace?.timings && workspace.timings.length > 0) {
    for (const t of workspace.timings) timings.set(t.scene_id, { duration: t.estimated_duration_seconds, start: t.start_seconds, end: t.end_seconds })
    return { timings, total: workspace.total_runtime_seconds ?? 0 }
  }
  let offset = 0
  for (const scene of workspace?.scenes ?? []) {
    const duration = estimateDuration(scene.body)
    timings.set(scene.id, { duration, start: offset, end: offset + duration })
    offset += duration
  }
  return { timings, total: offset }
}

function focusedBlockId(): number | null {
  const active = document.activeElement
  return active instanceof HTMLTextAreaElement && active.dataset.blockId ? Number(active.dataset.blockId) : null
}

function ExportLinks({ projectId, screenplayId }: { projectId: number; screenplayId: number }) {
  const base = `/api/v1/projects/${projectId}/screenplays/${screenplayId}/exports`
  return <>
    <a className="button quiet" href={`${base}/pdf`}>PDF</a>
    <a className="button quiet" href={`${base}/fountain`}>Fountain</a>
    <a className="button quiet" href={`${base}/fdx`}>FDX</a>
    <a className="button quiet" href={`${base}/html`}>HTML</a>
  </>
}

function BackupDrawer({ projectId, backups, onRestore }: { projectId: number; backups: ProjectBackup[]; onRestore: (filename: string) => void }) {
  return <section className="backup-drawer" aria-label="Project backups">
    <div><p className="eyebrow warm">RECOVERY</p><h2>Project backups</h2><p>Restore always creates a new project. Your current draft is never overwritten.</p></div>
    {backups.length ? <div className="backup-list">{backups.map(backup => <article className="backup-row" key={backup.filename}>
      <div><strong>{backup.filename}</strong><small>{new Date(backup.manifest.created_at).toLocaleString()} · SHA-256 {backup.manifest.sha256.slice(0, 12)}…</small></div>
      <div>
        <a className="button quiet" href={`/api/v1/projects/${projectId}/backups/${encodeURIComponent(backup.filename)}`}>Download</a>
        <button className="button primary" onClick={() => onRestore(backup.filename)}>Restore copy</button>
      </div>
    </article>)}</div> : <p className="empty-copy">No backups yet. Create one from the workspace header.</p>}
  </section>
}

function FormatToolbar({ onWrap, onColor }: { onWrap: (wrapper: string) => void; onColor: () => void }) {
  return <div className="format-toolbar" aria-label="Screenplay formatting toolbar">
    <span className="format-toolbar-label">Format:</span>
    <button type="button" className="mini-button format-action-btn" onClick={() => onWrap('**')} aria-label="Bold text" title="Bold (**text**)"><b>B</b></button>
    <button type="button" className="mini-button format-action-btn" onClick={() => onWrap('*')} aria-label="Italic text" title="Italic (*text*)"><i>I</i></button>
    <button type="button" className="mini-button format-action-btn" onClick={() => onWrap('_')} aria-label="Underline text" title="Underline (_text_)"><u>U</u></button>
    <button type="button" className="mini-button format-action-btn color-action-btn" onClick={onColor} aria-label="Amber mark" title="Amber accent mark"><span className="color-swatch" /></button>
  </div>
}

function HeadingOptions() {
  return <datalist id="screenplay-headings"><option value="INT. - DAY" /><option value="INT. - NIGHT" /><option value="EXT. - DAY" /><option value="EXT. - NIGHT" /><option value="INT./EXT. - DAY" /></datalist>
}

export default function Workspace({ projectId, initialTimeline = false }: WorkspaceProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const { data: workspace, error: loadError } = useWorkspace(projectId)
  const [view, setView] = useEditorView()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [projectInstruction, setProjectInstruction] = useState('')
  const [sceneInstruction, setSceneInstruction] = useState('')
  const [translationLanguage, setTranslationLanguage] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [timelineOpen, setTimelineOpen] = useState(initialTimeline)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const serverText = useRef<Record<number, string>>({})
  const [translationDraft, setTranslationDraft] = useState('')
  const [backupStatus, setBackupStatus] = useState('')
  const [backups, setBackups] = useState<ProjectBackup[]>([])
  const [backupsOpen, setBackupsOpen] = useState(false)
  const [importStatus, setImportStatus] = useState('')
  const [sceneHeading, setSceneHeading] = useState('')
  const [activeBlockId, setActiveBlockId] = useState<number | null>(null)
  const [deletingScene, setDeletingScene] = useState<Scene | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.workspaces(projectId) })
  const fail = (reason: unknown, fallback: string) => setError(errorMessage(reason, fallback))

  // Keep a valid scene selected: the one named in ?scene=, else the first.
  useEffect(() => {
    if (!workspace) return
    if (selectedId !== null && workspace.scenes.some(scene => scene.id === selectedId)) return
    const wanted = Number(params.get('scene'))
    setSelectedId(workspace.scenes.find(scene => scene.id === wanted)?.id ?? workspace.scenes[0]?.id ?? null)
  }, [workspace, selectedId, params])

  // Live sync: the project shell refetches the workspace; here we only surface what changed elsewhere.
  useEffect(() => subscribeProjectEvents(projectId, event => {
    if (event.client === CLIENT_ID) return
    if (event.kind === 'scene.changed') setNotice('Screenplay updated from another session or agent')
  }), [projectId])

  // Fold refetched block text into the editors: take the server's text when it changed, but never under the cursor.
  useEffect(() => {
    if (!workspace) return
    const editing = focusedBlockId()
    const blocks = Object.values(workspace.blocks).flat()
    setDrafts(previous => Object.fromEntries(blocks.map(block => {
      const changed = serverText.current[block.id] !== block.text
      const keep = block.id === editing || !changed
      return [block.id, keep ? previous[block.id] ?? block.text : block.text]
    })))
    serverText.current = Object.fromEntries(blocks.map(block => [block.id, block.text]))
  }, [workspace])

  const selectedScene: Scene | undefined = workspace?.scenes.find(scene => scene.id === selectedId)
  useChatFocus('screenplay', selectedScene?.heading ?? null, selectedScene?.id ?? null)
  // Follow ?scene= when it changes while the editor is open (the chat's open_scene tool, links from the outline).
  const sceneParam = Number(params.get('scene'))
  useEffect(() => {
    if (sceneParam && workspace?.scenes.some(scene => scene.id === sceneParam)) setSelectedId(sceneParam)
  }, [sceneParam, workspace])
  useEffect(() => { setSceneHeading(selectedScene?.heading ?? '') }, [selectedScene?.id, selectedScene?.heading])
  useEffect(() => { setProjectInstruction(workspace?.project.project_instruction ?? '') }, [workspace?.project.id, workspace?.project.project_instruction])
  useEffect(() => { setSceneInstruction(selectedScene?.scene_instruction ?? '') }, [selectedScene?.id, selectedScene?.scene_instruction])
  useEffect(() => {
    if (!workspace || projectInstruction === (workspace.project.project_instruction ?? '')) return
    const timer = window.setTimeout(() => {
      void updateProject(projectId, workspace.project.version, projectInstruction).then(refresh).catch(reason => fail(reason, 'Unable to save project instruction'))
    }, 500)
    return () => window.clearTimeout(timer)
  }, [projectId, workspace?.project.id, workspace?.project.version, workspace?.project.project_instruction, projectInstruction])
  useEffect(() => {
    if (!selectedScene || sceneInstruction === (selectedScene.scene_instruction ?? '')) return
    const timer = window.setTimeout(() => {
      void updateProjectScene(projectId, selectedScene.id, selectedScene.version, { scene_instruction: sceneInstruction }).then(refresh).catch(reason => fail(reason, 'Unable to save scene instruction'))
    }, 500)
    return () => window.clearTimeout(timer)
  }, [projectId, selectedScene?.id, selectedScene?.version, selectedScene?.scene_instruction, sceneInstruction])
  const dialogueBlock = selectedScene ? workspace?.blocks?.[selectedScene.id]?.find(block => block.element_type === 'dialogue') : undefined
  useEffect(() => {
    if (!selectedScene || !dialogueBlock || !translationLanguage) { setTranslationDraft(''); return }
    void getDialogueTranslations(projectId, selectedScene.id, dialogueBlock.id).then(items => {
      setTranslationDraft(items.find(item => item.language === translationLanguage)?.text ?? '')
    }).catch(() => setTranslationDraft(''))
  }, [dialogueBlock?.id, projectId, selectedScene?.id, translationLanguage])

  async function mutate(change: () => Promise<unknown>, fallback: string): Promise<void> {
    try { await change() } catch (reason) { fail(reason, fallback) }
    await refresh()
  }

  async function saveBlock(scene: Scene, block: ScreenplayBlock): Promise<void> {
    const draftText = drafts[block.id] ?? block.text
    const elementType = inferElement(draftText, block.element_type) ?? block.element_type
    if (draftText === block.text && elementType === block.element_type) return
    await mutate(() => updateProjectBlock(projectId, scene.id, block.id, scene.version, { text: draftText, element_type: elementType }), 'Unable to save screenplay block')
  }
  function changeBlockType(scene: Scene, block: ScreenplayBlock, elementType: string): void {
    if (elementType === block.element_type) return
    const text = drafts[block.id] ?? block.text
    void mutate(() => updateProjectBlock(projectId, scene.id, block.id, scene.version, { element_type: elementType, text }), 'Unable to change the block type')
  }
  function moveBlock(scene: Scene, index: number, delta: -1 | 1): void {
    const ids = (workspace?.blocks[scene.id] ?? []).map(block => block.id)
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    void mutate(() => reorderProjectBlocks(projectId, scene.id, scene.version, ids), 'Unable to reorder blocks')
  }
  function removeBlock(scene: Scene, block: ScreenplayBlock): void {
    if (!window.confirm('Delete this block? Its dialogue translations are deleted too.')) return
    void mutate(() => deleteProjectBlock(projectId, scene.id, block.id, scene.version), 'Unable to delete block')
  }
  function switchDraft(screenplayId: number): void {
    const next = new URLSearchParams(params)
    next.set('draft', String(screenplayId))
    next.delete('scene')
    setParams(next, { replace: true })
    setSelectedId(null)
  }
  async function saveTranslation(): Promise<void> {
    if (!selectedScene || !dialogueBlock || !translationLanguage) return
    try { await saveDialogueTranslation(projectId, selectedScene.id, dialogueBlock.id, translationLanguage, selectedScene.version, translationDraft) }
    catch (reason) { fail(reason, 'Unable to save dialogue translation') }
  }
  async function saveSceneHeading(): Promise<void> {
    if (!selectedScene || !sceneHeading.trim() || sceneHeading === selectedScene.heading) return
    await mutate(() => updateProjectScene(projectId, selectedScene.id, selectedScene.version, { heading: sceneHeading.trim() }), 'Unable to save scene heading')
  }
  async function backupProject(): Promise<void> {
    try {
      const backup = await createProjectBackup(projectId)
      setBackups(current => [backup, ...current.filter(item => item.filename !== backup.filename)])
      setBackupStatus(`Backup ready: ${backup.filename}`)
    } catch (reason) { setBackupStatus(reason instanceof Error ? reason.message : 'Backup failed') }
  }
  async function toggleBackups(): Promise<void> {
    if (!backupsOpen) {
      try { setBackups(await listProjectBackups(projectId)) } catch (reason) { setBackupStatus(reason instanceof Error ? reason.message : 'Unable to load backups') }
    }
    setBackupsOpen(open => !open)
  }
  async function restoreBackup(filename: string): Promise<void> {
    try {
      const restored = await restoreProjectBackup(projectId, filename)
      void queryClient.invalidateQueries({ queryKey: keys.projects })
      navigate(`/projects/${restored.project_id}`)
    } catch (reason) { setBackupStatus(reason instanceof Error ? reason.message : 'Unable to restore backup') }
  }
  async function importFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0]
    const screenplayId = workspace?.screenplay?.id
    if (!file || !screenplayId) return
    const filename = file.name.toLowerCase()
    const format = filename.endsWith('.fdx') ? 'fdx' : filename.endsWith('.pdf') ? 'pdf' : 'fountain'
    try {
      const content = format === 'pdf' ? await file.arrayBuffer() : await file.text()
      const imported = await importScreenplay(projectId, screenplayId, format, content)
      setImportStatus(`Imported as ${imported.title}`)
      await refresh()
      switchDraft(imported.id)
    } catch (reason) {
      setImportStatus(reason instanceof Error ? reason.message : 'Import failed')
    } finally { event.target.value = '' }
  }

  function wrapSelection(open: string, close: string, fallback: string): void {
    if (activeBlockId === null) return
    const blockId = activeBlockId
    const textarea = document.querySelector<HTMLTextAreaElement>(`textarea[data-block-id="${blockId}"]`)
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const currentText = drafts[blockId] ?? ''
    const selected = currentText.slice(start, end) || fallback
    setDrafts(previous => ({ ...previous, [blockId]: currentText.slice(0, start) + `${open}${selected}${close}` + currentText.slice(end) }))
    textarea.focus()
    // Reselect once React has written the new text, unless the writer has already moved on (a Tab, a click).
    setTimeout(() => { if (document.activeElement === textarea) textarea.setSelectionRange(start + open.length, start + open.length + selected.length) }, 0)
  }

  function sceneMoves(scene: Scene): SceneMoves {
    if (!workspace) return { toAct: () => undefined, remove: () => undefined }
    const acts = [...workspace.acts].sort((a, b) => a.position - b.position)
    const at = acts.findIndex(act => act.id === scene.act_id)
    const inAct = (actId: number) => workspace.scenes.filter(item => item.act_id === actId).length
    const move = (position: number, actId?: number) => void mutate(() => storyApi.moveScene(projectId, scene.id, scene.version, position, actId), 'Unable to move the scene')
    const previous = acts[at - 1]
    const next = acts[at + 1]
    return {
      up: scene.position > 0 ? () => move(scene.position - 1) : previous ? () => move(inAct(previous.id), previous.id) : undefined,
      down: scene.position < inAct(scene.act_id) - 1 ? () => move(scene.position + 1) : next ? () => move(0, next.id) : undefined,
      toAct: actId => { if (actId !== scene.act_id) move(inAct(actId), actId) },
      remove: () => setDeletingScene(scene),
    }
  }

  function deleteScene(scene: Scene): void {
    setDeletingScene(null)
    void mutate(async () => {
      await storyApi.deleteScene(projectId, scene.id, scene.version)
      setSelectedId(null)
      void queryClient.invalidateQueries({ queryKey: keys.beats(projectId) })
    }, 'Unable to delete the scene')
  }

  const { timings, total: totalRuntime } = sceneTimings(workspace)
  const targetRuntime = workspace?.target_runtime_seconds ?? 6600

  if (loadError || (error && !workspace)) return <main className="workspace-error"><p>{error || errorMessage(loadError, 'Unable to load workspace')}</p><button className="button primary" onClick={() => navigate('/projects')}>Back to projects</button></main>
  if (!workspace) return <main className="workspace-loading"><span className="status-dot" /> Opening your workspace…</main>

  const otherLanguages = workspace.project.languages.filter(language => language !== workspace.project.primary_language)
  const sceneBlocks = selectedScene ? workspace.blocks[selectedScene.id] ?? [] : []
  return <div className="workspace-shell">
    <header className="workspace-topbar">
      <div className="workspace-left">
        <button className="back-link" onClick={() => navigate('/projects')}>← Projects</button>
        <nav className="workspace-nav" aria-label="Project tools">
          <button className={timelineOpen ? 'active' : ''} onClick={() => setTimelineOpen(open => !open)}>{timelineOpen ? '← Editor' : 'Timeline'}</button>
          <Link to={`/projects/${projectId}/room`}>Writers’ room</Link>
          <Link to={`/projects/${projectId}/twin`}>Story twin</Link>
          <Link to={`/projects/${projectId}/outline`}>Outline</Link>
          <Link to={`/projects/${projectId}/studio`}>Story studio</Link>
        </nav>
      </div>
      <div>
        <p className="eyebrow warm">SCREENPLAY / {workspace.screenplay?.status ?? 'DRAFT'}</p>
        <h1>{workspace.project.title}</h1>
        <p className="workspace-language">Writing language: {workspace.project.primary_language} · Dialogue translations: {otherLanguages.length || 'none'} enabled</p>
      </div>
      <div className="save-state">
        <label className="button quiet import-button">Import<input type="file" accept=".fountain,.fdx,.pdf,text/plain,application/xml,application/pdf" onChange={event => void importFile(event)} /></label>
        {workspace.screenplay && <ExportLinks projectId={projectId} screenplayId={workspace.screenplay.id} />}
        <button className="button quiet" onClick={() => void backupProject()}>Backup</button>
        <button className="button quiet" onClick={() => void toggleBackups()} aria-expanded={backupsOpen}>Backups</button>
        {backupStatus && <small>{backupStatus}</small>}
        {importStatus && <small>{importStatus}</small>}
        <span className="status-dot" /> All changes local
      </div>
    </header>
    {backupsOpen && <BackupDrawer projectId={projectId} backups={backups} onRestore={filename => void restoreBackup(filename)} />}
    {notice && <div className="notice" role="status">{notice}<button type="button" onClick={() => setNotice('')}>×</button></div>}
    {error && <div className="notice" role="alert">{error}<button type="button" onClick={() => setError('')} aria-label="Dismiss">×</button></div>}
    <HeadingOptions />
    {timelineOpen ? <Timeline projectId={projectId} screenplayId={workspace.screenplay?.id ?? 0} workspace={workspace} /> : <div className="workspace-grid">
      <SceneNavigator projectId={projectId} workspace={workspace} selectedId={selectedId} onSelect={setSelectedId}
        timings={timings} totalRuntime={totalRuntime} targetRuntime={targetRuntime} moves={selectedScene ? sceneMoves(selectedScene) : null} />
      <main className="script-canvas">
        <div className="canvas-toolbar">
          {(workspace.screenplays?.length ?? 0) > 1
            ? <label className="draft-switcher">Draft <select aria-label="Screenplay draft" value={workspace.screenplay?.id ?? ''} onChange={event => switchDraft(Number(event.target.value))}>{workspace.screenplays?.map(draft => <option key={draft.id} value={draft.id}>{draft.title}</option>)}</select></label>
            : <span>{workspace.screenplay?.format ?? 'feature'} draft</span>}
          <button type="button" className="view-switch" role="switch" aria-checked={view === 'continuous'} onClick={() => setView(view === 'continuous' ? 'paginated' : 'continuous')}>
            Continuous view <i className={view === 'continuous' ? 'toggle on' : 'toggle'} aria-hidden="true" />
          </button>
        </div>
        {selectedScene ? <article className="script-page">
          <input className="script-heading" list="screenplay-headings" value={sceneHeading} onChange={event => setSceneHeading(event.target.value)} onBlur={() => void saveSceneHeading()} aria-label="Edit scene heading" />
          {sceneBlocks.length ? <div className="semantic-blocks">{sceneBlocks.map((block, index) => <BlockRow key={block.id} block={block} index={index} count={sceneBlocks.length}
            draft={drafts[block.id] ?? block.text} onDraft={text => setDrafts(previous => ({ ...previous, [block.id]: text }))}
            onFocus={() => setActiveBlockId(block.id)} onBlur={() => void saveBlock(selectedScene, block)}
            onTypeChange={elementType => changeBlockType(selectedScene, block, elementType)}
            onMove={delta => moveBlock(selectedScene, index, delta)} onDelete={() => removeBlock(selectedScene, block)} />)}</div>
            : <p className="script-body">{selectedScene.body || 'Begin writing this scene…'}</p>}
          <FormatToolbar onWrap={wrapper => wrapSelection(wrapper, wrapper, 'text')} onColor={() => wrapSelection('[[color:#dda05d]]', '[[/color]]', 'colored')} />
          <BlockCreationPanel key={selectedScene.id} projectId={projectId} scene={selectedScene} />
          <datalist id="screenplay-characters">{sceneBlocks.filter(block => block.element_type === 'character' && block.text.trim()).map(block => <option value={block.text} key={block.id} />)}</datalist>
          <div className="script-cursor" />
        </article> : <article className="script-page empty-script">
          <span>✦</span><h2>Your first scene starts here.</h2><p>Create a scene to begin shaping the screenplay.</p>
          {workspace.screenplay && <SceneCreationPanel projectId={projectId} screenplayId={workspace.screenplay.id} onCreated={setSelectedId} first />}
        </article>}
      </main>
      <aside className="context-panel">
        <div className="panel-label"><span>Context</span><span className="context-badge">Inherited</span></div>
        <section className="context-card"><p className="eyebrow warm">PROJECT INSTRUCTION</p><textarea value={projectInstruction} onChange={event => setProjectInstruction(event.target.value)} placeholder="What should every scene remember?" /><small>Applies to the whole project</small></section>
        <section className="context-card"><p className="eyebrow warm">SCENE INSTRUCTION</p><textarea value={sceneInstruction} onChange={event => setSceneInstruction(event.target.value)} placeholder="Tone, camera, light, or blocking for this scene…" /><small>{selectedScene ? 'Applies to the selected scene' : 'Select a scene to scope this instruction'}</small></section>
        <section className="context-card translation-card">
          <p className="eyebrow warm">DIALOGUE TRANSLATION</p>
          <select aria-label="Dialogue translation language" value={translationLanguage} onChange={event => setTranslationLanguage(event.target.value)}><option value="">Choose a language</option>{otherLanguages.map(language => <option key={language}>{language}</option>)}</select>
          {translationLanguage && dialogueBlock && <textarea value={translationDraft} onChange={event => setTranslationDraft(event.target.value)} onBlur={() => void saveTranslation()} placeholder={`Translate dialogue into ${translationLanguage}…`} aria-label={`Edit ${translationLanguage} translation`} />}
          <small>Only dialogue changes language. Headings and action remain in {workspace.project.primary_language}.</small>
        </section>
        <div className="context-links">
          <p className="eyebrow">Creative context</p>
          <Link to={`/projects/${projectId}/twin`}>✦ Story twin</Link>
          <Link to={`/projects/${projectId}/context`}>＋ Knowledge graph</Link>
          <Link to={`/projects/${projectId}/context?kind=reference_scene`}>＋ Reference scene</Link>
          <Link to={`/projects/${projectId}/context?kind=color_palette`}>＋ Color palette</Link>
          <Link to={`/projects/${projectId}/context?kind=camera`}>＋ Camera & lighting</Link>
          <Link to={`/projects/${projectId}/context?kind=film`}>＋ Film / director / style</Link>
        </div>
        {selectedScene && workspace.screenplay && <RevisionPanel projectId={projectId} sceneId={selectedScene.id} sceneVersion={selectedScene.version} screenplayId={workspace.screenplay.id} />}
        <McpApprovals projectId={projectId} />
      </aside>
    </div>}
    {deletingScene && <ConfirmDialog title={`Delete ${deletingScene.heading}?`} confirmLabel="Delete scene" onCancel={() => setDeletingScene(null)} onConfirm={() => deleteScene(deletingScene)}>
      <p>The scene, its blocks and its snapshots are removed. Beats and timeline events that pointed at it lose the link.</p>
    </ConfirmDialog>}
  </div>
}
