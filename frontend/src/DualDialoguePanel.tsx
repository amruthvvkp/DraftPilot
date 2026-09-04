import { useEffect, useState } from 'react'
import { getProjectWorkspace, ScreenplayBlock, updateProjectBlock } from './api'

type DualDialoguePanelProps = { projectId: number; sceneId: number }

export default function DualDialoguePanel({ projectId, sceneId }: DualDialoguePanelProps) {
  const [dialogues, setDialogues] = useState<ScreenplayBlock[]>([])
  const [version, setVersion] = useState(0)
  const [error, setError] = useState('')

  async function refresh(): Promise<void> {
    try {
      const workspace = await getProjectWorkspace(projectId)
      const scene = workspace.scenes.find(item => item.id === sceneId)
      const nextDialogues = (workspace.blocks[sceneId] ?? []).filter(item => item.element_type === 'dialogue')
      setDialogues(nextDialogues)
      setVersion(scene?.version ?? 0)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load dialogue controls')
    }
  }

  useEffect(() => { void refresh() }, [projectId, sceneId])

  async function toggle(): Promise<void> {
    const block = dialogues[0]
    if (!block || !version) return
    try {
      const paired = block.is_dual ? dialogues.filter(item => item.dual_group === block.dual_group) : dialogues.slice(0, 2)
      if (!block.is_dual && paired.length < 2) {
        setError('Add a second dialogue block before pairing')
        return
      }
      let currentVersion = version
      const group = block.dual_group ?? block.id
      for (const item of paired) {
        await updateProjectBlock(projectId, sceneId, item.id, currentVersion, {
          is_dual: !block.is_dual,
          dual_group: block.is_dual ? null : group,
        })
        currentVersion += 1
      }
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to update dual dialogue')
    }
  }

  const block = dialogues[0]
  if (!block) return null
  const isPaired = block.is_dual && dialogues.filter(item => item.dual_group === block.dual_group).length > 1
  return <section className="dual-dialogue-panel" aria-label="Dual dialogue"><div><p className="eyebrow warm">DIALOGUE LAYOUT</p><strong>{isPaired ? 'Paired dual dialogue' : 'Single dialogue'}</strong><small>{isPaired ? `Group ${block.dual_group ?? block.id} · ${dialogues.filter(item => item.dual_group === block.dual_group).length} linked blocks · source preserved` : dialogues.length > 1 ? 'Pair the first two dialogue blocks in this scene.' : 'Add a second dialogue block to enable pairing.'}</small></div><button className="mini-button" onClick={() => void toggle()} disabled={!isPaired && dialogues.length < 2}>{isPaired ? 'Unpair' : 'Pair dialogue'}</button>{error && <p className="copilot-error">{error}</p>}</section>
}
