import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Header from './components/Header'
import MainDashboard from './pages/MainDashboard'
import PositionsPage from './pages/PositionsPage'
import OrdersPage from './pages/OrdersPage'
import AlgorithmsPage from './pages/AlgorithmsPage'
import { SocketProvider } from './contexts/SocketContext'
import { DataProvider } from './contexts/DataContext'
import './App.css'

// Error Boundary Component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('React Error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <h1>Bir hata oluştu</h1>
          <p>{this.state.error?.message || 'Bilinmeyen hata'}</p>
          <button onClick={() => window.location.reload()}>Sayfayı Yenile</button>
          <pre style={{ marginTop: '20px', textAlign: 'left', background: '#f5f5f5', padding: '10px' }}>
            {this.state.error?.stack}
          </pre>
        </div>
      )
    }

    return this.props.children
  }
}

function App() {
  console.log('[App] Rendering...')
  
  try {
    return (
      <ErrorBoundary>
        <SocketProvider>
          <DataProvider>
            <Router>
              <div className="app">
                <Header />
                <main className="main-content">
                  <Routes>
                    <Route path="/" element={<MainDashboard />} />
                    <Route path="/positions" element={<PositionsPage />} />
                    <Route path="/orders" element={<OrdersPage />} />
                    <Route path="/algorithms" element={<AlgorithmsPage />} />
                  </Routes>
                </main>
                <Toaster position="top-right" />
              </div>
            </Router>
          </DataProvider>
        </SocketProvider>
      </ErrorBoundary>
    )
  } catch (error) {
    console.error('[App] Render error:', error)
    return (
      <div style={{ padding: '20px' }}>
        <h1>Uygulama yüklenirken hata oluştu</h1>
        <p>{error.message}</p>
        <pre>{error.stack}</pre>
      </div>
    )
  }
}

export default App

