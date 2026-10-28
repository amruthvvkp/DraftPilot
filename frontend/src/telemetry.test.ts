import { afterEach, describe, expect, it, vi } from 'vitest'
import { initTelemetry, recordNavigation, resetTelemetryForTests, routeName, stripUrl, TRACE_URL } from './telemetry'

type Sdk = Awaited<ReturnType<NonNullable<Parameters<typeof initTelemetry>[0]>>>

function serverSays(enabled: boolean) {
  const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify({ enabled, service_name: 'draftpilot-browser', service_version: '1.0.0', environment: 'local' }), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function fakeSdk() {
  const sdk = { configure: vi.fn(), info: vi.fn() }
  return { sdk, load: vi.fn(async () => sdk as unknown as Sdk) }
}

afterEach(() => {
  resetTelemetryForTests()
  vi.unstubAllGlobals()
})

describe('initTelemetry', () => {
  it('never loads the SDK when the server has telemetry off', async () => {
    const fetchMock = serverSays(false)
    const { sdk, load } = fakeSdk()
    expect(await initTelemetry(load)).toBe(false)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/telemetry/config')
    expect(load).not.toHaveBeenCalled()
    recordNavigation('/projects/3/script')
    expect(sdk.info).not.toHaveBeenCalled()
  })

  it('stays off when the config cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const { load } = fakeSdk()
    expect(await initTelemetry(load)).toBe(false)
    expect(load).not.toHaveBeenCalled()
  })

  it('exports through the same-origin proxy with no credentials when enabled', async () => {
    serverSays(true)
    const { sdk, load } = fakeSdk()
    expect(await initTelemetry(load)).toBe(true)
    expect(await initTelemetry(load)).toBe(true)
    expect(sdk.configure).toHaveBeenCalledTimes(1)
    const options = sdk.configure.mock.calls[0][0]
    expect(options.traceUrl).toBe(TRACE_URL)
    expect(options.serviceName).toBe('draftpilot-browser')
    expect(options.traceExporterHeaders).toBeUndefined()
    expect(options.sessionReplay).toBeUndefined()
    expect(JSON.stringify(options)).not.toMatch(/token|authorization/i)
    recordNavigation('/projects/3/characters/7')
    expect(sdk.info).toHaveBeenCalledWith('navigate {route}', { route: '/projects/:id/characters/:id' })
  })
})

describe('privacy helpers', () => {
  it('reduces paths to templates and strips queries and fragments', () => {
    expect(routeName('/projects/12/script/')).toBe('/projects/:id/script')
    expect(routeName('/')).toBe('/')
    expect(stripUrl('https://studio.local/api/v1/search?q=secret#frag')).toBe('https://studio.local/api/v1/search')
  })
})
