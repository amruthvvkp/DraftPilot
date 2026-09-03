import { useEffect, useState } from 'react'
import { getProjectWorkspace, ProjectWorkspace, Scene, updateProjectBlock } from './api'
import Timeline from './Timeline'
import CopilotPanel from './CopilotPanel'

type WorkspaceProps = { projectId: number }

export default function Workspace({ projectId }: WorkspaceProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [projectInstruction, setProjectInstruction] = useState('')
  const [sceneInstruction, setSceneInstruction] = useState('')
  const [translationLanguage, setTranslationLanguage] = useState('')
  const [error, setError] = useState('')
  const [timelineOpen, setTimelineOpen] = useState(false)
  const [draftText, setDraftText] = useState('')

  useEffect(() => {
    void getProjectWorkspace(projectId).then(data => {
      setWorkspace(data)
      setSelectedId(data.scenes[0]?.id ?? null)
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load workspace'))
  }, [projectId])

  const selectedScene: Scene | undefined = workspace?.scenes.find(scene => scene.id === selectedId)
  const selectedBlock = selectedScene ? workspace?.blocks?.[selectedScene.id]?.[0] : undefined
  useEffect(() => { setDraftText(selectedBlock?.text ?? '') }, [selectedBlock?.id, selectedBlock?.text])

  async function saveBlock(): Promise<void> {
    if (!selectedScene || !selectedBlock || draftText === selectedBlock.text) return
    try {
      await updateProjectBlock(projectId, selectedScene.id, selectedBlock.id, selectedScene.version, draftText)
      const refreshed = await getProjectWorkspace(projectId)
      setWorkspace(refreshed)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save screenplay block')
    }
  }
  if (error) return <main className="workspace-error"><p>{error}</p><button className="button primary" onClick={() => window.location.assign('/projects')}>Back to projects</button></main>
  if (!workspace) return <main className="workspace-loading"><span className="status-dot" /> Opening your workspace…</main>

  return <div className="workspace-shell">
    <header className="workspace-topbar">
      <button className="back-link" onClick={() => window.location.assign('/projects')}>← Projects</button>
      <div><p className="eyebrow warm">SCREENPLAY / {workspace.screenplay?.status ?? 'DRAFT'}</p><h1>{workspace.project.title}</h1><p className="workspace-language">Writing language: {workspace.project.primary_language} · Dialogue translations: {workspace.project.languages.length || 'none'} enabled</p></div>
      <div className="save-state"><span className="status-dot" /> All changes local</div>
    </header>
    {timelineOpen ? <Timeline projectId={projectId} screenplayId={workspace.screenplay?.id ?? 0} workspace={workspace} /> : <div className="workspace-grid">
      <aside className="navigator"><div className="panel-label"><span>Navigator</span><span>{workspace.scenes.length.toString().padStart(2, '0')} scenes</span></div>
        {workspace.acts.length === 0 && <p className="empty-copy">Your scene list will appear here as the story takes shape.</p>}
        {workspace.acts.map(act => <div className="act-group" key={act.id}><p className="act-title">{act.title || `Act ${act.position + 1}`}</p>{workspace.scenes.filter(scene => scene.act_id === act.id).map(scene => <button className={scene.id === selectedId ? 'scene-link selected' : 'scene-link'} key={scene.id} onClick={() => setSelectedId(scene.id)}><span>{String(scene.position + 1).padStart(2, '0')}</span><strong>{scene.heading}</strong></button>)}</div>)}
      </aside>
      <main className="script-canvas"><div className="canvas-toolbar"><span>{workspace.screenplay?.format ?? 'feature'} draft</span><span>Continuous view <i className="toggle on" /></span></div>{selectedScene ? <article className="script-page"><p className="script-heading">{selectedScene.heading}</p>{selectedBlock ? <textarea className={`script-editor ${selectedBlock.element_type}`} value={draftText} onChange={event => setDraftText(event.target.value)} onBlur={() => void saveBlock()} aria-label={`Edit ${selectedBlock.element_type}`} /> : <p className="script-body">{selectedScene.body || 'Begin writing this scene…'}</p>}<div className="script-cursor" /></article> : <article className="script-page empty-script"><span>✦</span><h2>Your first scene starts here.</h2><p>Create a scene to begin shaping the screenplay.</p></article>}</main>
      <aside className="context-panel"><div className="panel-label"><span>Context</span><span className="context-badge">Inherited</span></div><section className="context-card"><p className="eyebrow warm">PROJECT INSTRUCTION</p><textarea value={projectInstruction} onChange={event => setProjectInstruction(event.target.value)} placeholder="What should every scene remember?" /><small>Applies to the whole project</small></section><section className="context-card"><p className="eyebrow warm">SCENE INSTRUCTION</p><textarea value={sceneInstruction} onChange={event => setSceneInstruction(event.target.value)} placeholder="Tone, camera, light, or blocking for this scene…" /><small>{selectedScene ? 'Applies to the selected scene' : 'Select a scene to scope this instruction'}</small></section><section className="context-card translation-card"><p className="eyebrow warm">DIALOGUE TRANSLATION</p><select value={translationLanguage} onChange={event => setTranslationLanguage(event.target.value)}><option value="">Choose a language</option>{workspace.project.languages.filter(language => language !== workspace.project.primary_language).map(language => <option key={language}>{language}</option>)}</select><small>Only dialogue changes language. Headings and action remain in {workspace.project.primary_language}.</small></section><div className="context-links"><p className="eyebrow">Creative context</p><button>＋ Reference scene</button><button>＋ Color palette</button><button>＋ Camera & lighting</button><button>＋ Film / director / style</button></div><CopilotPanel projectId={projectId} /></aside>
    </div>}
    <button className="timeline-launch" onClick={() => setTimelineOpen(open => !open)}>{timelineOpen ? '← Editor' : 'Timeline board →'}</button>
  </div>
}
