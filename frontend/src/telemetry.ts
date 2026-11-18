// Browser telemetry (G12): Logfire's browser SDK, exporting through the API's same-origin OTLP proxy.
// Off unless the server reports OTEL__ENABLED; the SDK is a lazy chunk that never loads when it is off.
// No exporter credential ever reaches the browser: the proxy sits behind the API session cookie.
import { getTelemetryConfig, type TelemetryConfig } from './api'

export const TRACE_URL = '/api/v1/telemetry/v1/traces'
export const METRIC_URL = '/api/v1/telemetry/v1/metrics'
const PROXY = /\/api\/v1\/telemetry\//

type LogfireBrowser = typeof import('@pydantic/logfire-browser')
type Loader = () => Promise<LogfireBrowser>

let active: LogfireBrowser | null = null
let starting: Promise<boolean> | null = null

/** Collapse ids out of a path (`/projects/12/script` → `/projects/:id/script`) for low-cardinality route names. */
export function routeName(pathname: string): string {
  return pathname.replace(/\/\d+(?=\/|$)/g, '/:id').replace(/\/+$/, '') || '/'
}

/** Drop the query string and fragment from a URL, which may carry search text or tokens. */
export function stripUrl(url: string): string {
  return url.split(/[?#]/, 1)[0]
}

/** Configure the SDK: fetch/XHR spans propagate `traceparent` to the same-origin API, so they join its traces. */
function configure(logfire: LogfireBrowser, config: TelemetryConfig): void {
  const scrubUrl = (span: { setAttribute: (key: string, value: string) => unknown }, url: string) => {
    span.setAttribute('http.url', stripUrl(url))
    span.setAttribute('url.full', stripUrl(url))
  }
  logfire.configure({
    traceUrl: TRACE_URL,
    serviceName: config.service_name,
    serviceVersion: config.service_version,
    environment: config.environment,
    metrics: { metricUrl: METRIC_URL },
    resourceTiming: { detail: 'summary' },
    rum: { session: { getRouteName: () => routeName(window.location.pathname) }, webVitals: true },
    autoInstrumentations: {
      '@opentelemetry/instrumentation-fetch': {
        ignoreUrls: [PROXY],
        applyCustomAttributesOnSpan: (span, request) => {
          const url = typeof request === 'string' ? request : request instanceof Request ? request.url : ''
          if (url) scrubUrl(span, new URL(url, window.location.origin).href)
        },
      },
      '@opentelemetry/instrumentation-xml-http-request': {
        ignoreUrls: [PROXY],
        applyCustomAttributesOnSpan: (span, xhr) => { if (xhr.responseURL) scrubUrl(span, xhr.responseURL) },
      },
    },
  })
}

/**
 * Start browser telemetry once, if the server has it on. Resolves to whether it is active.
 * A failed config read leaves telemetry off and lets a later call retry.
 */
export function initTelemetry(load: Loader = () => import('@pydantic/logfire-browser')): Promise<boolean> {
  if (!starting) {
    starting = (async () => {
      const config = await getTelemetryConfig().catch(() => null)
      if (!config?.enabled) {
        starting = null
        return false
      }
      const logfire = await load()
      configure(logfire, config)
      active = logfire
      return true
    })()
  }
  return starting
}

/** Record a client-side route change (path template only) when telemetry is active. */
export function recordNavigation(pathname: string): void {
  active?.info('navigate {route}', { route: routeName(pathname) })
}

/** Forget the started SDK; tests only. */
export function resetTelemetryForTests(): void {
  active = null
  starting = null
}
