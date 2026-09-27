import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import AuthGate from './SignIn'
import './theme.css'
import './styles.css'
import { initAppearance } from './theme'

initAppearance()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </StrictMode>,
)
