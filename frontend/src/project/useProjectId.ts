import { useParams } from 'react-router'

/** Read the numeric project id from the `/projects/:projectId/...` route. */
export function useProjectId(): number {
  const { projectId } = useParams()
  return Number(projectId)
}
