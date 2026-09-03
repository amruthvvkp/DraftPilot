import { useEffect, useState } from 'react'
import { getProjectWorkspace, ScreenplayBlock, updateProjectBlock } from './api'

type DualDialoguePanelProps = { projectId: number; sceneId: number }

export default function DualDialoguePanel({ projectId, sceneId }: DualDialoguePanelProps) {
  const [block, setBlock] = useState<ScreenplayBlock | null>(null)
  const [version, setVersion] = useState(0)
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try {
      const workspace = await getProjectWorkspace(projectId)
      const scene = workspace.scenes.find(item => item.id === sceneId)
      const dialogue = (workspace.blocks[sceneId] ?? []).find(item => item.element_type === 'dialogue')
      setBlock(dialogue ?? null)
      setVersion(scene?.version ?? 0)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load dialogue controls')
    }
  }

  useEffect(() => { void refresh() }, [projectId, sceneId])

  async function toggle(): Promise<void> {
    if (!block || !version) return
    try {
      const updated = await updateProjectBlock(projectId, sceneId, block.id, version, {
        is_dual: !block.is_dual,
        dual_group: block.dual_group ?? block.id,
      })
      setBlock(updated)
      setVersion(version + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to update dual dialogue')
    }
  }

  if (!block) return null
  return <section className="dual-dialogue-panel" aria-label="Dual dialogue"><div><p className="eyebrow warm">DIALOGUE LAYOUT</p><strong>{block.is_dual ? 'Paired dual dialogue' : 'Single dialogue'}</strong><small>{block.is_dual ? `Group ${block.dual_group ?? block.id} · source preserved` : 'Pair this speech with a second dialogue block.'}</small></div><button className="mini-button" onClick={() => void toggle()}>{block.is_dual ? 'Unpair' : 'Pair dialogue'}</button>{error && <p className="copilot-error">{error}</p>}</section>
}
