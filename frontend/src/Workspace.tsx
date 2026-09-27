import './room.css'
import { type ChangeEvent, type KeyboardEvent, useEffect, useState } from 'react'
import { CLIENT_ID, selectDraft, createAgentProposal, createProjectBackup, deleteProjectBlock, reorderProjectBlocks, subscribeProjectEvents, getDialogueTranslations, getProjectWorkspace, importScreenplay, listProjectBackups, ProjectBackup, ProjectWorkspace, restoreProjectBackup, saveDialogueTranslation, Scene, ScreenplayBlock, updateProject, updateProjectBlock, updateProjectScene } from './api'
import Timeline from './Timeline'
import CopilotPanel from './CopilotPanel'
import McpApprovals from './McpApprovals'
import RevisionPanel from './RevisionPanel'
import './backup.css'

type WorkspaceProps = { projectId: number }

function advanceEditor(event: KeyboardEvent<HTMLTextAreaElement>): void {
  if (event.key !== 'Tab' || event.shiftKey) return
  event.preventDefault()
  const editors = Array.from(document.querySelectorAll<HTMLTextAreaElement>('.script-editor'))
  const next = editors[editors.indexOf(event.currentTarget) + 1]
  next?.focus()
}

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

function estimateDuration(body: string): number {
  return Math.max(30, Math.round(body.split(/\s+/).filter(Boolean).length / 2))
}

function getSceneStatus(scene: Scene, blockList: ScreenplayBlock[] | undefined): 'ready' | 'in progress' | 'needs content' {
  if (!scene.body.trim() && (!blockList || blockList.length === 0)) return 'needs content'
  const hasDialogue = blockList?.some(b => b.element_type === 'dialogue')
  const hasCharacter = blockList?.some(b => b.element_type === 'character')
  if (hasDialogue && hasCharacter) return 'ready'
  return 'in progress'
}

export default function Workspace({ projectId }: WorkspaceProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [projectInstruction, setProjectInstruction] = useState('')
  const [sceneInstruction, setSceneInstruction] = useState('')
  const [translationLanguage, setTranslationLanguage] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [timelineOpen, setTimelineOpen] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [translationDraft, setTranslationDraft] = useState('')
  const [backupStatus, setBackupStatus] = useState('')
  const [backups, setBackups] = useState<ProjectBackup[]>([])
  const [backupsOpen, setBackupsOpen] = useState(false)
  const [importStatus, setImportStatus] = useState('')
  const [sceneHeading, setSceneHeading] = useState('')
  const [formatDrafts, setFormatDrafts] = useState<Record<number, string>>({})
  const [proposalRefresh, setProposalRefresh] = useState(0)
  const [activeBlockId, setActiveBlockId] = useState<number | null>(null)

  useEffect(() => {
    void getProjectWorkspace(projectId).then(data => {
      setWorkspace(data)
      setSelectedId(data.scenes[0]?.id ?? null)
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load workspace'))
  }, [projectId])

  useEffect(() => {
    let timer: number | undefined
    const unsubscribe = subscribeProjectEvents(projectId, event => {
      if (event.client === CLIENT_ID) return
      if (event.kind === 'proposal.changed' || event.kind === 'run.changed') setProposalRefresh(value => value + 1)
      if (!['scene.changed', 'proposal.changed', 'timeline.changed', 'translation.changed'].includes(event.kind)) return
      window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        void getProjectWorkspace(projectId).then(refreshed => {
          const editing = document.activeElement instanceof HTMLTextAreaElement ? Number(document.activeElement.dataset.blockId) : null
          setWorkspace(refreshed)
          setDrafts(previous => Object.fromEntries(Object.values(refreshed.blocks).flat().map(block => [block.id, block.id === editing ? previous[block.id] ?? block.text : block.text])))
          setFormatDrafts(Object.fromEntries(Object.values(refreshed.blocks).flat().map(block => [block.id, block.element_type])))
          if (event.kind === 'scene.changed') setNotice('Screenplay updated from another session or agent')
        }).catch(() => undefined)
      }, 250)
    })
    return () => { window.clearTimeout(timer); unsubscribe() }
  }, [projectId])

  const selectedScene: Scene | undefined = workspace?.scenes.find(scene => scene.id === selectedId)
  useEffect(() => { setSceneHeading(selectedScene?.heading ?? '') }, [selectedScene?.id, selectedScene?.heading])
  useEffect(() => { setProjectInstruction(workspace?.project.project_instruction ?? '') }, [workspace?.project.id, workspace?.project.project_instruction])
  useEffect(() => { setSceneInstruction(selectedScene?.scene_instruction ?? '') }, [selectedScene?.id, selectedScene?.scene_instruction])
  useEffect(() => {
    if (!workspace || projectInstruction === (workspace.project.project_instruction ?? '')) return
    const timer = window.setTimeout(() => {
      void updateProject(projectId, workspace.project.version, projectInstruction).then(() => getProjectWorkspace(projectId).then(setWorkspace)).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to save project instruction'))
    }, 500)
    return () => window.clearTimeout(timer)
  }, [projectId, workspace?.project.id, workspace?.project.version, workspace?.project.project_instruction, projectInstruction])
  useEffect(() => {
    if (!selectedScene || sceneInstruction === (selectedScene.scene_instruction ?? '')) return
    const timer = window.setTimeout(() => {
      void updateProjectScene(projectId, selectedScene.id, selectedScene.version, { scene_instruction: sceneInstruction }).then(() => getProjectWorkspace(projectId).then(setWorkspace)).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to save scene instruction'))
    }, 500)
    return () => window.clearTimeout(timer)
  }, [projectId, selectedScene?.id, selectedScene?.version, selectedScene?.scene_instruction, sceneInstruction])
  useEffect(() => {
    if (!workspace) return
    setDrafts(previous => Object.fromEntries(Object.values(workspace.blocks).flat().map(block => [block.id, previous[block.id] ?? block.text])))
    setFormatDrafts(previous => Object.fromEntries(Object.values(workspace.blocks).flat().map(block => [block.id, previous[block.id] ?? block.element_type])))
  }, [workspace])
  const dialogueBlock = selectedScene ? workspace?.blocks?.[selectedScene.id]?.find(block => block.element_type === 'dialogue') : undefined
  useEffect(() => {
    if (!selectedScene || !dialogueBlock || !translationLanguage) {
      setTranslationDraft('')
      return
    }
    void getDialogueTranslations(projectId, selectedScene.id, dialogueBlock.id).then(items => {
      setTranslationDraft(items.find(item => item.language === translationLanguage)?.text ?? '')
    }).catch(() => setTranslationDraft(''))
  }, [dialogueBlock?.id, projectId, selectedScene?.id, translationLanguage])

  async function saveBlock(scene: Scene, block: ScreenplayBlock, elementType?: string): Promise<void> {
    const draftText = drafts[block.id] ?? block.text
    if (draftText === block.text && (!elementType || elementType === block.element_type)) return
    try {
      await updateProjectBlock(projectId, scene.id, block.id, scene.version, { text: draftText, element_type: elementType ?? block.element_type })
      const refreshed = await getProjectWorkspace(projectId)
      setWorkspace(refreshed)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save screenplay block')
    }
  }
  async function moveBlock(scene: Scene, index: number, delta: -1 | 1): Promise<void> {
    const ids = (workspace?.blocks[scene.id] ?? []).map(block => block.id)
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    try { await reorderProjectBlocks(projectId, scene.id, scene.version, ids); setWorkspace(await getProjectWorkspace(projectId)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to reorder blocks') }
  }
  async function removeBlock(scene: Scene, block: ScreenplayBlock): Promise<void> {
    if (!window.confirm('Delete this block? Its dialogue translations are deleted too.')) return
    try { await deleteProjectBlock(projectId, scene.id, block.id, scene.version); setWorkspace(await getProjectWorkspace(projectId)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to delete block') }
  }
  async function switchDraft(screenplayId: number): Promise<void> {
    try {
      const refreshed = await getProjectWorkspace(projectId, screenplayId)
      selectDraft(screenplayId)
      setWorkspace(refreshed)
      setSelectedId(refreshed.scenes[0]?.id ?? null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to open draft')
    }
  }
  async function saveTranslation(): Promise<void> {
    if (!selectedScene || !dialogueBlock || !translationLanguage) return
    try {
      await saveDialogueTranslation(projectId, selectedScene.id, dialogueBlock.id, translationLanguage, selectedScene.version, translationDraft)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save dialogue translation')
    }
  }
  async function saveSceneHeading(): Promise<void> {
    if (!selectedScene || !sceneHeading.trim() || sceneHeading === selectedScene.heading) return
    try {
      await updateProjectScene(projectId, selectedScene.id, selectedScene.version, { heading: sceneHeading.trim() })
      setWorkspace(await getProjectWorkspace(projectId))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save scene heading')
    }
  }
  async function proposeBlockFormat(scene: Scene, block: ScreenplayBlock): Promise<void> {
    const elementType = formatDrafts[block.id] ?? block.element_type
    if (elementType === block.element_type) return
    try {
      await createAgentProposal(projectId, {
        target_kind: 'block', target_id: block.id, scene_id: scene.id,
        operation: { element_type: elementType },
        diff: { field: 'element_type', from: block.element_type, to: elementType },
        base_version: scene.version,
      })
      setProposalRefresh(value => value + 1)
      setNotice('Formatting proposal ready for review in Copilot.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to propose screenplay formatting')
    }
  }
  async function backupProject(): Promise<void> {
    try {
      const backup = await createProjectBackup(projectId)
      setBackups(current => [backup, ...current.filter(item => item.filename !== backup.filename)])
      setBackupStatus(`Backup ready: ${backup.filename}`)
    } catch (reason) {
      setBackupStatus(reason instanceof Error ? reason.message : 'Backup failed')
    }
  }
  async function toggleBackups(): Promise<void> {
    if (!backupsOpen) {
      try { setBackups(await listProjectBackups(projectId)) }
      catch (reason) { setBackupStatus(reason instanceof Error ? reason.message : 'Unable to load backups') }
    }
    setBackupsOpen(open => !open)
  }
  async function restoreBackup(filename: string): Promise<void> {
    try {
      const restored = await restoreProjectBackup(projectId, filename)
      window.location.assign(`/projects/${restored.project_id}`)
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
      await switchDraft(imported.id)
    } catch (reason) {
      setImportStatus(reason instanceof Error ? reason.message : 'Import failed')
    } finally {
      event.target.value = ''
    }
  }

  function applyFormat(wrapper: string): void {
    if (activeBlockId === null) return
    const textarea = document.querySelector<HTMLTextAreaElement>(`textarea[data-block-id="${activeBlockId}"]`)
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const currentText = drafts[activeBlockId] ?? ''
    const selected = currentText.slice(start, end) || 'text'
    const newText = currentText.slice(0, start) + `${wrapper}${selected}${wrapper}` + currentText.slice(end)
    setDrafts(previous => ({ ...previous, [activeBlockId]: newText }))
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + wrapper.length, start + wrapper.length + selected.length)
    }, 0)
  }

  function applyColor(hex: string): void {
    if (activeBlockId === null) return
    const textarea = document.querySelector<HTMLTextAreaElement>(`textarea[data-block-id="${activeBlockId}"]`)
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const currentText = drafts[activeBlockId] ?? ''
    const selected = currentText.slice(start, end) || 'colored'
    const newText = currentText.slice(0, start) + `[[color:${hex}]]${selected}[[/color]]` + currentText.slice(end)
    setDrafts(previous => ({ ...previous, [activeBlockId]: newText }))
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + `[[color:${hex}]]`.length, start + `[[color:${hex}]]`.length + selected.length)
    }, 0)
  }

  const timingMap = new Map<number, { duration: number; start: number; end: number }>()
  let totalRuntime = 0
  if (workspace?.timings && workspace.timings.length > 0) {
    for (const t of workspace.timings) {
      timingMap.set(t.scene_id, {
        duration: t.estimated_duration_seconds,
        start: t.start_seconds,
        end: t.end_seconds,
      })
    }
    totalRuntime = workspace.total_runtime_seconds ?? 0
  } else if (workspace?.scenes) {
    let offset = 0
    for (const scene of workspace.scenes) {
      const d = estimateDuration(scene.body)
      timingMap.set(scene.id, { duration: d, start: offset, end: offset + d })
      offset += d
    }
    totalRuntime = offset
  }
  const targetRuntime = workspace?.target_runtime_seconds ?? 6600
  const progressPercent = Math.min(100, Math.round((totalRuntime / targetRuntime) * 100))
  const driftSeconds = totalRuntime - targetRuntime
  const pacingDrift = totalRuntime === 0 ? 'Not started' : Math.abs(driftSeconds) <= 300 ? 'On pace' : driftSeconds > 0 ? `+${Math.round(driftSeconds / 60)}m ahead` : `-${Math.round(Math.abs(driftSeconds) / 60)}m behind`

  if (error) return <main className="workspace-error"><p>{error}</p><button className="button primary" onClick={() => window.location.assign('/projects')}>Back to projects</button></main>
  if (!workspace) return <main className="workspace-loading"><span className="status-dot" /> Opening your workspace…</main>

  return <div className="workspace-shell">
    <header className="workspace-topbar">
      <div className="workspace-left"><button className="back-link" onClick={() => window.location.assign('/projects')}>← Projects</button><nav className="workspace-nav" aria-label="Project tools"><button className={timelineOpen ? 'active' : ''} onClick={() => setTimelineOpen(open => !open)}>{timelineOpen ? '← Editor' : 'Timeline'}</button><a href={`/projects/${projectId}/room`}>Writers’ room</a><a href={`/projects/${projectId}/twin`}>Story twin</a><a href={`/projects/${projectId}/beats`}>Beat board</a><a href={`/projects/${projectId}/studio`}>Story studio</a></nav></div>
      <div><p className="eyebrow warm">SCREENPLAY / {workspace.screenplay?.status ?? 'DRAFT'}</p><h1>{workspace.project.title}</h1><p className="workspace-language">Writing language: {workspace.project.primary_language} · Dialogue translations: {workspace.project.languages.filter(language => language !== workspace.project.primary_language).length || 'none'} enabled</p></div>
      <div className="save-state"><label className="button quiet import-button">Import<input type="file" accept=".fountain,.fdx,.pdf,text/plain,application/xml,application/pdf" onChange={event => void importFile(event)} /></label>{workspace.screenplay && <><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/pdf`}>PDF</a><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/fountain`}>Fountain</a><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/fdx`}>FDX</a><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/html`}>HTML</a></>}<button className="button quiet" onClick={() => void backupProject()}>Backup</button><button className="button quiet" onClick={() => void toggleBackups()} aria-expanded={backupsOpen}>Backups</button>{backupStatus && <small>{backupStatus}</small>}{importStatus && <small>{importStatus}</small>}<span className="status-dot" /> All changes local</div>
    </header>
    {backupsOpen && <section className="backup-drawer" aria-label="Project backups"><div><p className="eyebrow warm">RECOVERY</p><h2>Project backups</h2><p>Restore always creates a new project. Your current draft is never overwritten.</p></div>{backups.length ? <div className="backup-list">{backups.map(backup => <article className="backup-row" key={backup.filename}><div><strong>{backup.filename}</strong><small>{new Date(backup.manifest.created_at).toLocaleString()} · SHA-256 {backup.manifest.sha256.slice(0, 12)}…</small></div><div><a className="button quiet" href={`/api/v1/projects/${projectId}/backups/${encodeURIComponent(backup.filename)}`}>Download</a><button className="button primary" onClick={() => void restoreBackup(backup.filename)}>Restore copy</button></div></article>)}</div> : <p className="empty-copy">No backups yet. Create one from the workspace header.</p>}</section>}
    {notice && <div className="notice" role="status">{notice}<button type="button" onClick={() => setNotice('')}>×</button></div>}
    {timelineOpen ? <Timeline projectId={projectId} screenplayId={workspace.screenplay?.id ?? 0} workspace={workspace} /> : <div className="workspace-grid">
      <aside className="navigator"><div className="panel-label"><span>Navigator</span><span>{workspace.scenes.length.toString().padStart(2, '0')} scenes</span></div>
        <div className="runtime-summary" aria-label="Screenplay runtime">
          <div className="runtime-numbers">
            <span>Estimated runtime</span>
            <strong>{clock(totalRuntime)} / {clock(targetRuntime)}</strong>
          </div>
          <div className="runtime-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100} aria-label="Runtime progress">
            <div className="runtime-fill" style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="runtime-meta">
            <small className="runtime-drift">Pacing: {pacingDrift}</small>
            <small className="runtime-note">Scene time accumulates as the draft grows.</small>
          </div>
        </div>
        {workspace.acts.length === 0 && <p className="empty-copy">Your scene list will appear here as the story takes shape.</p>}
        {workspace.acts.map(act => <div className="act-group" key={act.id}><p className="act-title">{act.title || `Act ${act.position + 1}`}</p>{workspace.scenes.filter(scene => scene.act_id === act.id).map(scene => {
          const timing = timingMap.get(scene.id) ?? { duration: 30, start: 0, end: 30 }
          const status = getSceneStatus(scene, workspace.blocks[scene.id])
          return <button className={scene.id === selectedId ? 'scene-link selected' : 'scene-link'} key={scene.id} onClick={() => setSelectedId(scene.id)}>
            <div className="scene-link-header">
              <span>{String(scene.position + 1).padStart(2, '0')}</span>
              <strong>{scene.heading}</strong>
              <span className="scene-duration">{clock(timing.duration)}</span>
            </div>
            <div className="scene-link-meta">
              <small>{clock(timing.start)}–{clock(timing.end)} · {status}</small>
            </div>
          </button>
        })}</div>)}
      </aside>
      <main className="script-canvas"><div className="canvas-toolbar">{(workspace.screenplays?.length ?? 0) > 1 ? <label className="draft-switcher">Draft <select aria-label="Screenplay draft" value={workspace.screenplay?.id ?? ''} onChange={event => void switchDraft(Number(event.target.value))}>{workspace.screenplays?.map(draft => <option key={draft.id} value={draft.id}>{draft.title}</option>)}</select></label> : <span>{workspace.screenplay?.format ?? 'feature'} draft</span>}<span>Continuous view <i className="toggle on" /></span></div>{selectedScene ? <article className="script-page"><input className="script-heading" list="screenplay-headings" value={sceneHeading} onChange={event => setSceneHeading(event.target.value)} onBlur={() => void saveSceneHeading()} aria-label="Edit scene heading" />{workspace.blocks?.[selectedScene.id]?.length ? <div className="semantic-blocks">{workspace.blocks[selectedScene.id].map((block, index, list) => <div className={block.is_dual ? 'semantic-row dual-block' : 'semantic-row'} key={block.id}><select className="element-selector" value={formatDrafts[block.id] ?? block.element_type} onChange={event => setFormatDrafts(previous => ({ ...previous, [block.id]: event.target.value }))} aria-label={`Format ${block.element_type}`}><option value="action">Action</option><option value="character">Character</option><option value="dialogue">Dialogue</option><option value="parenthetical">Parenthetical</option><option value="transition">Transition</option><option value="lyric">Lyric</option><option value="note">Note</option><option value="section">Section</option><option value="synopsis">Synopsis</option><option value="shot">Shot</option><option value="page_break">Page break</option></select><button type="button" className="mini-button format-proposal" onClick={() => void proposeBlockFormat(selectedScene, block)} disabled={(formatDrafts[block.id] ?? block.element_type) === block.element_type}>Review format</button>{block.element_type === 'page_break' ? <div className="page-break-marker" role="separator" aria-label="Page break"><span>page break</span></div> : <textarea className={`script-editor ${block.element_type}`} data-block-id={block.id} onFocus={() => setActiveBlockId(block.id)} list={block.element_type === 'character' ? 'screenplay-characters' : undefined} value={drafts[block.id] ?? block.text} onChange={event => setDrafts(previous => ({ ...previous, [block.id]: event.target.value }))} onKeyDown={advanceEditor} onBlur={() => void saveBlock(selectedScene, block)} aria-label={`Edit ${block.element_type}`} aria-keyshortcuts="Tab" />}<div className="block-actions" role="group" aria-label={`Block ${index + 1} actions`}>{block.origin && block.origin !== 'human' && <span className="block-origin" title="Last authored by">{block.origin.startsWith('proposal:') ? 'agent' : block.origin}</span>}<button type="button" className="mini-button" onClick={() => void moveBlock(selectedScene, index, -1)} disabled={index === 0} aria-label={`Move block ${index + 1} up`}>↑</button><button type="button" className="mini-button" onClick={() => void moveBlock(selectedScene, index, 1)} disabled={index === list.length - 1} aria-label={`Move block ${index + 1} down`}>↓</button><button type="button" className="mini-button danger" onClick={() => void removeBlock(selectedScene, block)} aria-label={`Delete block ${index + 1}`}>✕</button></div></div>)}</div> : <p className="script-body">{selectedScene.body || 'Begin writing this scene…'}</p>}<div className="format-toolbar" aria-label="Screenplay formatting toolbar"><span className="format-toolbar-label">Format:</span><button type="button" className="mini-button format-action-btn" onClick={() => applyFormat('**')} aria-label="Bold text" title="Bold (**text**)"><b>B</b></button><button type="button" className="mini-button format-action-btn" onClick={() => applyFormat('*')} aria-label="Italic text" title="Italic (*text*)"><i>I</i></button><button type="button" className="mini-button format-action-btn" onClick={() => applyFormat('_')} aria-label="Underline text" title="Underline (_text_)"><u>U</u></button><button type="button" className="mini-button format-action-btn color-action-btn" onClick={() => applyColor('#dda05d')} aria-label="Amber mark" title="Amber accent mark"><span className="color-swatch" /></button></div><datalist id="screenplay-headings"><option value="INT. - DAY" /><option value="INT. - NIGHT" /><option value="EXT. - DAY" /><option value="EXT. - NIGHT" /><option value="INT./EXT. - DAY" /></datalist><datalist id="screenplay-characters">{workspace.blocks[selectedScene.id]?.filter(block => block.element_type === 'character' && block.text.trim()).map(block => <option value={block.text} key={block.id} />)}</datalist><div className="script-cursor" /></article> : <article className="script-page empty-script"><span>✦</span><h2>Your first scene starts here.</h2><p>Create a scene to begin shaping the screenplay.</p></article>}</main>
      <aside className="context-panel"><div className="panel-label"><span>Context</span><span className="context-badge">Inherited</span></div><section className="context-card"><p className="eyebrow warm">PROJECT INSTRUCTION</p><textarea value={projectInstruction} onChange={event => setProjectInstruction(event.target.value)} placeholder="What should every scene remember?" /><small>Applies to the whole project</small></section><section className="context-card"><p className="eyebrow warm">SCENE INSTRUCTION</p><textarea value={sceneInstruction} onChange={event => setSceneInstruction(event.target.value)} placeholder="Tone, camera, light, or blocking for this scene…" /><small>{selectedScene ? 'Applies to the selected scene' : 'Select a scene to scope this instruction'}</small></section><section className="context-card translation-card"><p className="eyebrow warm">DIALOGUE TRANSLATION</p><select aria-label="Dialogue translation language" value={translationLanguage} onChange={event => setTranslationLanguage(event.target.value)}><option value="">Choose a language</option>{workspace.project.languages.filter(language => language !== workspace.project.primary_language).map(language => <option key={language}>{language}</option>)}</select>{translationLanguage && dialogueBlock && <textarea value={translationDraft} onChange={event => setTranslationDraft(event.target.value)} onBlur={() => void saveTranslation()} placeholder={`Translate dialogue into ${translationLanguage}…`} aria-label={`Edit ${translationLanguage} translation`} />}<small>Only dialogue changes language. Headings and action remain in {workspace.project.primary_language}.</small></section><div className="context-links"><p className="eyebrow">Creative context</p><a href={`/projects/${projectId}/twin`}>✦ Story twin</a><a href={`/projects/${projectId}/context`}>＋ Knowledge graph</a><a href={`/projects/${projectId}/context?kind=reference_scene`}>＋ Reference scene</a><a href={`/projects/${projectId}/context?kind=color_palette`}>＋ Color palette</a><a href={`/projects/${projectId}/context?kind=camera`}>＋ Camera & lighting</a><a href={`/projects/${projectId}/context?kind=film`}>＋ Film / director / style</a></div>{!timelineOpen && selectedScene && workspace.screenplay && <RevisionPanel projectId={projectId} sceneId={selectedScene.id} sceneVersion={selectedScene.version} screenplayId={workspace.screenplay.id} />}<McpApprovals projectId={projectId} /><CopilotPanel projectId={projectId} page={`/projects/${projectId}/workspace`} artifact="screenplay" selection={selectedScene?.heading ?? null} refreshToken={proposalRefresh} /></aside>
    </div>}

  </div>
}
