import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { subscribeProjectEvents } from '../api'
import { invalidateForEvent } from './queries'

/** Keep every cached query of an open project fresh: live-sync events invalidate what they touch. */
export function useProjectLiveSync(projectId: number): void {
  const client = useQueryClient()
  useEffect(() => subscribeProjectEvents(projectId, event => invalidateForEvent(client, projectId, event)), [client, projectId])
}
