import { type ChangeEvent, type KeyboardEvent, useEffect, useState } from 'react'
import { createProjectBackup, getDialogueTranslations, getProjectWorkspace, importScreenplay, ProjectWorkspace, saveDialogueTranslation, Scene, ScreenplayBlock, updateProject, updateProjectBlock, updateProjectScene } from './api'
import Timeline from './Timeline'
import CopilotPanel from './CopilotPanel'
import RevisionPanel from './RevisionPanel'

type WorkspaceProps = { projectId: number }

function advanceEditor(event: KeyboardEvent<HTMLTextAreaElement>): void {
  if (event.key !== 'Tab' || event.shiftKey) return
  event.preventDefault()
  const editors = Array.from(document.querySelectorAll<HTMLTextAreaElement>('.script-editor'))
  const next = editors[editors.indexOf(event.currentTarget) + 1]
  next?.focus()
}

export default function Workspace({ projectId }: WorkspaceProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [projectInstruction, setProjectInstruction] = useState('')
  const [sceneInstruction, setSceneInstruction] = useState('')
  const [translationLanguage, setTranslationLanguage] = useState('')
  const [error, setError] = useState('')
  const [timelineOpen, setTimelineOpen] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [translationDraft, setTranslationDraft] = useState('')
  const [backupStatus, setBackupStatus] = useState('')
  const [importStatus, setImportStatus] = useState('')
  const [sceneHeading, setSceneHeading] = useState('')

  useEffect(() => {
    void getProjectWorkspace(projectId).then(data => {
      setWorkspace(data)
      setSelectedId(data.scenes[0]?.id ?? null)
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load workspace'))
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
  async function backupProject(): Promise<void> {
    try {
      const backup = await createProjectBackup(projectId)
      setBackupStatus(`Backup ready: ${backup.filename}`)
    } catch (reason) {
      setBackupStatus(reason instanceof Error ? reason.message : 'Backup failed')
    }
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
    } catch (reason) {
      setImportStatus(reason instanceof Error ? reason.message : 'Import failed')
    } finally {
      event.target.value = ''
    }
  }
  if (error) return <main className="workspace-error"><p>{error}</p><button className="button primary" onClick={() => window.location.assign('/projects')}>Back to projects</button></main>
  if (!workspace) return <main className="workspace-loading"><span className="status-dot" /> Opening your workspace…</main>

  return <div className="workspace-shell">
    <header className="workspace-topbar">
      <button className="back-link" onClick={() => window.location.assign('/projects')}>← Projects</button>
      <div><p className="eyebrow warm">SCREENPLAY / {workspace.screenplay?.status ?? 'DRAFT'}</p><h1>{workspace.project.title}</h1><p className="workspace-language">Writing language: {workspace.project.primary_language} · Dialogue translations: {workspace.project.languages.length || 'none'} enabled</p></div>
      <div className="save-state"><label className="button quiet import-button">Import<input type="file" accept=".fountain,.fdx,.pdf,text/plain,application/xml,application/pdf" onChange={event => void importFile(event)} /></label>{workspace.screenplay && <><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/pdf`}>PDF</a><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/fountain`}>Fountain</a><a className="button quiet" href={`/api/v1/projects/${projectId}/screenplays/${workspace.screenplay.id}/exports/fdx`}>FDX</a></>}<button className="button quiet" onClick={() => void backupProject()}>Backup</button>{backupStatus && <small>{backupStatus}</small>}{importStatus && <small>{importStatus}</small>}<span className="status-dot" /> All changes local</div>
    </header>
    {timelineOpen ? <Timeline projectId={projectId} screenplayId={workspace.screenplay?.id ?? 0} workspace={workspace} /> : <div className="workspace-grid">
      <aside className="navigator"><div className="panel-label"><span>Navigator</span><span>{workspace.scenes.length.toString().padStart(2, '0')} scenes</span></div>
        {workspace.acts.length === 0 && <p className="empty-copy">Your scene list will appear here as the story takes shape.</p>}
        {workspace.acts.map(act => <div className="act-group" key={act.id}><p className="act-title">{act.title || `Act ${act.position + 1}`}</p>{workspace.scenes.filter(scene => scene.act_id === act.id).map(scene => <button className={scene.id === selectedId ? 'scene-link selected' : 'scene-link'} key={scene.id} onClick={() => setSelectedId(scene.id)}><span>{String(scene.position + 1).padStart(2, '0')}</span><strong>{scene.heading}</strong></button>)}</div>)}
      </aside>
      <main className="script-canvas"><div className="canvas-toolbar"><span>{workspace.screenplay?.format ?? 'feature'} draft</span><span>Continuous view <i className="toggle on" /></span></div>{selectedScene ? <article className="script-page"><input className="script-heading" list="screenplay-headings" value={sceneHeading} onChange={event => setSceneHeading(event.target.value)} onBlur={() => void saveSceneHeading()} aria-label="Edit scene heading" />{workspace.blocks?.[selectedScene.id]?.length ? <div className="semantic-blocks">{workspace.blocks[selectedScene.id].map(block => <div className="semantic-row" key={block.id}><select className="element-selector" value={block.element_type} onChange={event => void saveBlock(selectedScene, block, event.target.value)} aria-label={`Format ${block.element_type}`}><option value="action">Action</option><option value="character">Character</option><option value="dialogue">Dialogue</option><option value="parenthetical">Parenthetical</option><option value="transition">Transition</option><option value="lyric">Lyric</option><option value="note">Note</option><option value="section">Section</option><option value="synopsis">Synopsis</option><option value="shot">Shot</option><option value="page_break">Page break</option></select><textarea className={`script-editor ${block.element_type}`} list={block.element_type === 'character' ? 'screenplay-characters' : undefined} value={drafts[block.id] ?? block.text} onChange={event => setDrafts(previous => ({ ...previous, [block.id]: event.target.value }))} onKeyDown={advanceEditor} onBlur={() => void saveBlock(selectedScene, block)} aria-label={`Edit ${block.element_type}`} aria-keyshortcuts="Tab" /></div>)}</div> : <p className="script-body">{selectedScene.body || 'Begin writing this scene…'}</p>}<datalist id="screenplay-headings"><option value="INT. - DAY" /><option value="INT. - NIGHT" /><option value="EXT. - DAY" /><option value="EXT. - NIGHT" /><option value="INT./EXT. - DAY" /></datalist><datalist id="screenplay-characters">{workspace.blocks[selectedScene.id]?.filter(block => block.element_type === 'character' && block.text.trim()).map(block => <option value={block.text} key={block.id} />)}</datalist><div className="script-cursor" /></article> : <article className="script-page empty-script"><span>✦</span><h2>Your first scene starts here.</h2><p>Create a scene to begin shaping the screenplay.</p></article>}</main>
      <aside className="context-panel"><div className="panel-label"><span>Context</span><span className="context-badge">Inherited</span></div><section className="context-card"><p className="eyebrow warm">PROJECT INSTRUCTION</p><textarea value={projectInstruction} onChange={event => setProjectInstruction(event.target.value)} placeholder="What should every scene remember?" /><small>Applies to the whole project</small></section><section className="context-card"><p className="eyebrow warm">SCENE INSTRUCTION</p><textarea value={sceneInstruction} onChange={event => setSceneInstruction(event.target.value)} placeholder="Tone, camera, light, or blocking for this scene…" /><small>{selectedScene ? 'Applies to the selected scene' : 'Select a scene to scope this instruction'}</small></section><section className="context-card translation-card"><p className="eyebrow warm">DIALOGUE TRANSLATION</p><select value={translationLanguage} onChange={event => setTranslationLanguage(event.target.value)}><option value="">Choose a language</option>{workspace.project.languages.filter(language => language !== workspace.project.primary_language).map(language => <option key={language}>{language}</option>)}</select>{translationLanguage && dialogueBlock && <textarea value={translationDraft} onChange={event => setTranslationDraft(event.target.value)} onBlur={() => void saveTranslation()} placeholder={`Translate dialogue into ${translationLanguage}…`} aria-label={`Edit ${translationLanguage} translation`} />}<small>Only dialogue changes language. Headings and action remain in {workspace.project.primary_language}.</small></section><div className="context-links"><p className="eyebrow">Creative context</p><a href={`/projects/${projectId}/context`}>＋ Knowledge graph</a><a href={`/projects/${projectId}/context?kind=reference_scene`}>＋ Reference scene</a><a href={`/projects/${projectId}/context?kind=color_palette`}>＋ Color palette</a><a href={`/projects/${projectId}/context?kind=camera`}>＋ Camera & lighting</a><a href={`/projects/${projectId}/context?kind=film`}>＋ Film / director / style</a></div><CopilotPanel projectId={projectId} page={`/projects/${projectId}/workspace`} artifact="screenplay" selection={selectedScene?.heading ?? null} /></aside>
    </div>}
    {!timelineOpen && selectedScene && workspace.screenplay && <RevisionPanel projectId={projectId} sceneId={selectedScene.id} sceneVersion={selectedScene.version} screenplayId={workspace.screenplay.id} />}<button className="studio-launch" onClick={() => window.location.assign(`/projects/${projectId}/studio`)}>Story studio ↗</button><button className="timeline-launch" onClick={() => setTimelineOpen(open => !open)}>{timelineOpen ? '← Editor' : 'Timeline board →'}</button>
  </div>
}
