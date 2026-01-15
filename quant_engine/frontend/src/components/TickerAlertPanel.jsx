import React, { useState, useEffect, useCallback } from 'react'
import './TickerAlertPanel.css'

/**
 * TickerAlertPanel - Displays session high/low alerts (Lightspeed-style)
 * 
 * Features:
 * - Shows NEW_HIGH and NEW_LOW events
 * - Tab-based session tracking (each tab tracks from its open time)
 * - Auto-refresh every 2 seconds
 * - Color-coded alerts (green for high, red for low)
 */
function TickerAlertPanel({ sessionId, onClose }) {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Fetch recent alerts
  const fetchAlerts = useCallback(async () => {
    if (!sessionId) return
    
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`/api/ticker-alerts/recent?limit=50`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const result = await response.json()
      if (result.success) {
        // Filter alerts for this session (if sessionId is provided)
        // For now, show all alerts (global session)
        setAlerts(result.alerts || [])
      } else {
        throw new Error(result.detail || 'Failed to fetch alerts')
      }
    } catch (err) {
      console.error('Error fetching ticker alerts:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // Auto refresh
  useEffect(() => {
    if (autoRefresh) {
      fetchAlerts()
      const interval = setInterval(fetchAlerts, 2000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, fetchAlerts])

  // Initial fetch
  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  // Listen to WebSocket for real-time ticker alerts
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/market-data')
    
    ws.onopen = () => {
      console.log('✅ Ticker Alert WebSocket connected')
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'ticker_alert') {
          // Add new alert to the list (prepend to show newest first)
          setAlerts(prevAlerts => {
            const newAlert = message.alert || message.data
            // Check if alert already exists (prevent duplicates)
            const exists = prevAlerts.some(
              a => a.symbol === newAlert.symbol && 
                   a.event_type === newAlert.event_type && 
                   a.timestamp === newAlert.timestamp
            )
            if (exists) {
              return prevAlerts
            }
            // Add new alert at the beginning
            return [newAlert, ...prevAlerts].slice(0, 100) // Keep last 100 alerts
          })
          console.log('🔔 New ticker alert:', message.data)
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err)
      }
    }
    
    ws.onerror = (error) => {
      console.error('Ticker Alert WebSocket error:', error)
    }
    
    ws.onclose = () => {
      console.log('Ticker Alert WebSocket disconnected')
    }
    
    return () => {
      ws.close()
    }
  }, [])

  // Reset session
  const handleResetSession = async () => {
    try {
      const response = await fetch('/api/ticker-alerts/session/reset', {
        method: 'POST'
      })
      if (response.ok) {
        await fetchAlerts()
      }
    } catch (err) {
      console.error('Error resetting session:', err)
    }
  }

  // Format timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return 'N/A'
    try {
      const date = new Date(timestamp)
      return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return timestamp
    }
  }

  // Format price change percentage
  const formatChangePct = (price, prevHigh, prevLow, eventType) => {
    if (!price) return 'N/A'
    
    let prevPrice = null
    if (eventType === 'NEW_HIGH' && prevHigh) {
      prevPrice = prevHigh
    } else if (eventType === 'NEW_LOW' && prevLow) {
      prevPrice = prevLow
    }
    
    if (!prevPrice || prevPrice === 0) return 'N/A'
    
    const changePct = ((price - prevPrice) / prevPrice) * 100
    return `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%`
  }

  return (
    <div className="ticker-alert-panel">
      <div className="ticker-alert-header">
        <h3>🔔 Ticker Alerts</h3>
        <div className="ticker-alert-controls">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`btn btn-sm ${autoRefresh ? 'btn-danger' : 'btn-success'}`}
          >
            {autoRefresh ? 'Stop' : 'Start'} Auto Refresh
          </button>
          <button
            onClick={handleResetSession}
            className="btn btn-sm btn-secondary"
            title="Reset session (clear high/low state)"
          >
            Reset Session
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="btn btn-sm btn-secondary"
            >
              Close
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="ticker-alert-error">
          Error: {error}
        </div>
      )}

      <div className="ticker-alert-stats">
        <span>Total Alerts: {alerts.length}</span>
        <span>High: {alerts.filter(a => a.event_type === 'NEW_HIGH').length}</span>
        <span>Low: {alerts.filter(a => a.event_type === 'NEW_LOW').length}</span>
      </div>

      <div className="ticker-alert-list">
        {loading && alerts.length === 0 ? (
          <div className="ticker-alert-loading">Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div className="ticker-alert-empty">No alerts yet. Waiting for new highs/lows...</div>
        ) : (
          <table className="ticker-alert-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Event</th>
                <th>Price</th>
                <th>Change %</th>
                <th>Prev High</th>
                <th>Prev Low</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert, idx) => (
                <tr
                  key={`${alert.symbol}-${alert.timestamp}-${idx}`}
                  className={`ticker-alert-row ticker-alert-${alert.event_type.toLowerCase()}`}
                >
                  <td>{formatTime(alert.timestamp)}</td>
                  <td className="ticker-alert-symbol">{alert.symbol}</td>
                  <td>
                    <span className={`ticker-alert-badge ticker-alert-badge-${alert.event_type.toLowerCase()}`}>
                      {alert.event_type === 'NEW_HIGH' ? '📈 HIGH' : '📉 LOW'}
                    </span>
                  </td>
                  <td className="ticker-alert-price">${alert.price?.toFixed(2) || 'N/A'}</td>
                  <td className="ticker-alert-change">
                    {formatChangePct(alert.price, alert.prev_high, alert.prev_low, alert.event_type)}
                  </td>
                  <td>${alert.prev_high?.toFixed(2) || 'N/A'}</td>
                  <td>${alert.prev_low?.toFixed(2) || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default TickerAlertPanel





