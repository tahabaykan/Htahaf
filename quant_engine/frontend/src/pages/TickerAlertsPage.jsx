import React, { useState, useEffect, useCallback } from 'react'
import { FixedSizeList as List } from 'react-window'
import './TickerAlertsPage.css'

function TickerAlertsPage() {
  const [alerts, setAlerts] = useState([]) // Panel starts EMPTY (Lightspeed-style)
  const [bcConnected, setBcConnected] = useState(false)
  const [pollingActive, setPollingActive] = useState(false)

  // Fetch alerts on mount (panel should be empty initially - only shows NEW_HIGH/NEW_LOW events)
  useEffect(() => {
    fetchAlerts()
    
    // Use BroadcastChannel to receive data from Scanner page (NO WebSocket)
    let broadcastChannel = null
    let pollingInterval = null
    
    try {
      broadcastChannel = new BroadcastChannel('market-data')
      setBcConnected(true)
      console.log('✅ BroadcastChannel connected (Ticker Alerts - Subscriber)')
      
      broadcastChannel.onmessage = (event) => {
        try {
          const message = event.data
          // Listen for ticker alert events from Scanner page
          if (message.type === 'ticker_alert') {
            const newAlert = message.alert
            if (newAlert) {
              setAlerts(prev => [newAlert, ...prev].slice(0, 1000)) // Keep last 1000
            }
          }
        } catch (err) {
          console.error('Error parsing BroadcastChannel message:', err)
        }
      }
      
      broadcastChannel.onerror = (error) => {
        console.error('BroadcastChannel error:', error)
        setBcConnected(false)
      }
    } catch (err) {
      console.warn('BroadcastChannel not supported, falling back to REST polling:', err)
      setBcConnected(false)
      
      // Fallback: REST polling every 2 seconds
      setPollingActive(true)
      pollingInterval = setInterval(() => {
        fetchAlerts()
      }, 2000)
    }
    
    return () => {
      if (broadcastChannel) {
        broadcastChannel.close()
      }
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [])

  const fetchAlerts = async () => {
    try {
      const response = await fetch('/api/ticker-alerts/recent?limit=100')
      const data = await response.json()
      if (data.success) {
        // Panel shows ONLY alerts (events), not baseline data
        setAlerts(data.alerts || [])
      }
    } catch (err) {
      console.error('Error fetching alerts:', err)
    }
  }

  // Refresh alerts periodically (only if BroadcastChannel is not available)
  useEffect(() => {
    if (!bcConnected && !pollingActive) {
      const interval = setInterval(() => {
        fetchAlerts()
      }, 2000) // Every 2 seconds (fallback)
      
      return () => clearInterval(interval)
    }
  }, [bcConnected, pollingActive])

  const Row = ({ index, style }) => {
    const alert = alerts[index]
    if (!alert) return null
    
    const isHigh = alert.event_type === 'NEW_HIGH'
    const isLow = alert.event_type === 'NEW_LOW'
    const color = isHigh ? '#00ff00' : isLow ? '#ff0000' : '#ffffff'
    
    // Format timestamp
    const timestamp = alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString() : ''
    
    // Format change
    const changeStr = alert.change !== null && alert.change !== undefined
      ? `${alert.change >= 0 ? '+' : ''}${alert.change.toFixed(2)}`
      : '-'
    const changePercentStr = alert.change_percent !== null && alert.change_percent !== undefined
      ? `(${alert.change_percent >= 0 ? '+' : ''}${alert.change_percent.toFixed(2)}%)`
      : ''
    
    return (
      <div style={{ ...style, display: 'flex', alignItems: 'center' }} className="ticker-alert-row">
        <div className="ticker-alert-cell symbol" style={{ width: 120, color }}>
          {alert.symbol}
        </div>
        <div className="ticker-alert-cell price" style={{ width: 100, color }}>
          ${alert.price.toFixed(2)}
        </div>
        <div className="ticker-alert-cell change" style={{ width: 150, color }}>
          {changeStr} {changePercentStr}
        </div>
        <div className="ticker-alert-cell time" style={{ width: 100, color }}>
          {timestamp}
        </div>
      </div>
    )
  }

  return (
    <div className="ticker-alerts-page">
      <div className="ticker-alerts-header">
        <h1>Ticker Alert</h1>
        <div className="ticker-alerts-controls">
          <button onClick={fetchAlerts}>Refresh</button>
          <button onClick={() => {
            // Reset session (reload baseline from CSV)
            fetch('/api/ticker-alerts/session/reset', { method: 'POST' })
              .then(() => {
                setAlerts([]) // Clear alerts
                fetchAlerts() // Reload
              })
          }}>Reset Session</button>
                  <span className={`ws-status ${bcConnected ? 'connected' : 'disconnected'}`}>
                    {bcConnected ? '🟢 BC Connected' : pollingActive ? '🔄 Polling' : '🔴 Disconnected'}
                  </span>
        </div>
      </div>
      
      <div className="ticker-alerts-table">
        <div className="ticker-alerts-table-header">
          <div className="ticker-alert-cell symbol" style={{ width: 120 }}>Symbol</div>
          <div className="ticker-alert-cell price" style={{ width: 100 }}>Price</div>
          <div className="ticker-alert-cell change" style={{ width: 150 }}>Change</div>
          <div className="ticker-alert-cell time" style={{ width: 100 }}>Time</div>
        </div>
        
        {alerts.length > 0 ? (
          <List
            height={600}
            itemCount={alerts.length}
            itemSize={30}
            width="100%"
          >
            {Row}
          </List>
        ) : (
          <div className="empty-state">
            <p>No ticker alerts yet. Waiting for daily high/low breakouts...</p>
            <p style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
              Panel starts empty (Lightspeed-style). Alerts appear when symbols break daily high/low from Hammer snapshot.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default TickerAlertsPage
