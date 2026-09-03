import { useEffect, useState } from 'react'
import { EvaluationResult, listEvaluations } from './api'

type EvaluationPanelProps = { projectId: number }

export default function EvaluationPanel({ projectId }: EvaluationPanelProps) {
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    void listEvaluations(projectId).then(setEvaluations).catch(reason => setError(reason instanceof Error ? reason.message : 'Unable to load evaluations'))
  }, [projectId])

  return <section className="evaluation-panel" aria-label="Story evaluations"><div className="panel-label"><span>Review signals</span><span>{evaluations.length}</span></div>{error && <p className="copilot-error">{error}</p>}{evaluations.length === 0 && !error && <p className="empty-copy">Evaluations will appear here after a review run.</p>}{evaluations.map(item => <article className="evaluation-card" key={item.id}><div><p className="eyebrow warm">{item.evaluator} · {item.target_kind}</p><strong>{item.score === null ? 'Unscored' : `${Math.round(item.score * 100)}% signal`}</strong></div><p>{item.summary}</p></article>)}</section>
}
