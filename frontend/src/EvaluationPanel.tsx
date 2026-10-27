import { useEffect, useState } from 'react'
import { EvaluationResult, getWorkflowRun, listEvaluations, startEvaluation } from './api'

type EvaluationPanelProps = { projectId: number; screenplayId: number }

export default function EvaluationPanel({ projectId, screenplayId }: EvaluationPanelProps) {
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([])
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    void listEvaluations(projectId).then(setEvaluations).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load evaluations'))
  }, [projectId])

  async function runReview(): Promise<void> {
    setRunning(true)
    setError('')
    try {
      const run = await startEvaluation(projectId, screenplayId)
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 250))
        const current = await getWorkflowRun(projectId, run.id)
        if (current.status === 'succeeded') {
          setEvaluations(await listEvaluations(projectId))
          return
        }
        if (current.status === 'failed' || current.status === 'cancelled') throw new Error(current.error ?? `Review ${current.status}`)
      }
      setError('Review is still running; results will appear when you return.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to run evaluation') }
    finally { setRunning(false) }
  }

  return <section className="evaluation-panel" aria-label="Story evaluations"><div className="panel-label"><span>Review signals</span><div><span>{evaluations.length}</span><button className="mini-button" onClick={() => void runReview()} disabled={running}>{running ? 'Reviewing…' : 'Run review'}</button></div></div>{error && <p className="copilot-error">{error}</p>}{evaluations.length === 0 && !error && <p className="empty-copy">Evaluations will appear here after a review run.</p>}{evaluations.map(item => <article className="evaluation-card" key={item.id}><div><p className="eyebrow warm">{item.evaluator} · {item.target_kind}</p><strong>{item.score === null ? 'Unscored' : `${Math.round(item.score * 100)}% signal`}</strong></div><p>{item.summary}</p></article>)}</section>
}
