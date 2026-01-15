import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

console.log('[main.jsx] Starting React app...')

try {
  const rootElement = document.getElementById('root')
  
  if (!rootElement) {
    throw new Error('Root element (#root) bulunamadı!')
  }

  console.log('[main.jsx] Root element bulundu, React render ediliyor...')
  
  const root = ReactDOM.createRoot(rootElement)
  
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
  
  console.log('[main.jsx] React app render edildi!')
} catch (error) {
  console.error('[main.jsx] Fatal error:', error)
  document.body.innerHTML = `
    <div style="padding: 20px; font-family: Arial;">
      <h1>Kritik Hata</h1>
      <p>${error.message}</p>
      <pre>${error.stack}</pre>
    </div>
  `
}

