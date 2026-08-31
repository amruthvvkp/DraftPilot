export type Project = {
  id: number
  title: string
  logline: string | null
  description: string | null
  genres: string[]
  languages: string[]
  artwork_url: string | null
}

export type ProjectCreatePayload = {
  title: string
  logline?: string | null
  description?: string | null
  story_outline?: string | null
  visual_style?: string | null
  camera_type?: string | null
  screening_type?: string | null
  artwork_url?: string | null
  genres: string[]
  languages: string[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json() as Promise<T>
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/api/v1/projects')
}

export function createProject(payload: ProjectCreatePayload): Promise<Project> {
  return request<Project>('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
