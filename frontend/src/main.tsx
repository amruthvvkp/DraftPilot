import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import AuthGate from './SignIn'
import RouteTelemetry from './RouteTelemetry'
import { createQueryClient } from './data/queries'
import './theme.css'
import './styles.css'
import { initAppearance } from './theme'
import { initTelemetry } from './telemetry'

initAppearance()
void initTelemetry()
const queryClient = createQueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <RouteTelemetry />
        <AuthGate>
          <App />
        </AuthGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
