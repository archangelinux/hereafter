import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// self-hosted type: nothing is fetched from a font CDN at demo time
import '@fontsource/cormorant-garamond/300.css'
import '@fontsource/cormorant-garamond/300-italic.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/500-italic.css'
import '@fontsource/cormorant-sc/400.css'
import '@fontsource/cormorant-sc/500.css'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'

import './styles.css'
import { applyTheme } from './theme'
import App from './App'

applyTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
