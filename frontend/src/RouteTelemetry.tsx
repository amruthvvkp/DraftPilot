import { useEffect } from 'react'
import { useLocation } from 'react-router'
import { recordNavigation } from './telemetry'

/** Emit a navigation record per route change; renders nothing and does nothing when telemetry is off. */
export default function RouteTelemetry() {
  const { pathname } = useLocation()
  useEffect(() => { recordNavigation(pathname) }, [pathname])
  return null
}
