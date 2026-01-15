import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './TradingPage.css'

function TradingExposure() {
  const navigate = useNavigate()
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')
  const [exposure, setExposure] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadTradingMode()
    loadExposure()
  }, [])

  useEffect(() => {
    loadExposure()
  }, [tradingMode])

  const loadTradingMode = async () => {
    try {
      const response = await fetch('/api/trading/mode')
      const result = await response.json()
      if (result.success) {
        setTradingMode(result.mode)
      }
    } catch (err) {
      console.error('Error loading trading mode:', err)
    }
  }

  const loadExposure = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/trading/exposure')
      const result = await response.json()
      if (result.success) {
        setExposure(result.exposure || null)
      }
    } catch (err) {
      console.error('Error loading exposure:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="trading-page">
      <div className="trading-page-header">
        <h1>Exposure</h1>
        <div className="trading-mode-badge">
          {tradingMode === 'HAMMER_TRADING' ? '🟢 Hammer Account' : '🟣 IBKR Account'}
        </div>
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Scanner
        </button>
      </div>

      <div className="trading-page-content">
        {loading && (
          <div className="loading-message">Loading exposure...</div>
        )}

        {!loading && !exposure && (
          <div className="empty-state">
            No exposure data for {tradingMode}
          </div>
        )}

        {!loading && exposure && (
          <div className="exposure-metrics">
            <div className="metric-card">
              <div className="metric-label">Total Exposure</div>
              <div className="metric-value large">
                ${exposure.total_exposure?.toFixed(2) || '0.00'}
              </div>
            </div>
            
            <div className="metric-card positive">
              <div className="metric-label">Long Exposure</div>
              <div className="metric-value large positive">
                ${exposure.long_exposure?.toFixed(2) || '0.00'}
              </div>
            </div>
            
            <div className="metric-card negative">
              <div className="metric-label">Short Exposure</div>
              <div className="metric-value large negative">
                ${exposure.short_exposure?.toFixed(2) || '0.00'}
              </div>
            </div>
            
            <div className={`metric-card ${exposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
              <div className="metric-label">Net Exposure</div>
              <div className={`metric-value large ${exposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                ${exposure.net_exposure?.toFixed(2) || '0.00'}
              </div>
            </div>
            
            <div className="metric-card">
              <div className="metric-label">Position Count</div>
              <div className="metric-value large">
                {exposure.position_count || 0}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TradingExposure








