import React, { useState, useEffect } from 'react'
import './LiveDataStatusBar.css'

/**
 * Live Data Status Bar - Shows live_data vs algo_ready status
 * 
 * Displays:
 * - Live data status (how many symbols have bid/ask/last)
 * - Algo ready status (can RUNALL start?)
 * - Real-time updates via WebSocket
 */
function LiveDataStatusBar() {
  const [stats, setStats] = useState({
    total_symbols: 0,
    symbols_with_live: 0,
    live_data_percent: 0,
    algo_ready: false,
    algo_reason: null
  })

  // Listen for live_view_stats updates via BroadcastChannel
  useEffect(() => {
    let bc = null
    
    try {
      bc = new BroadcastChannel('market-data')
      
      bc.onmessage = (event) => {
        try {
          const message = event.data
          if (message.type === 'live_view_stats' && message.data) {
            setStats(message.data)
          }
        } catch (err) {
          console.error('Error parsing live_view_stats:', err)
        }
      }
    } catch (err) {
      console.warn('BroadcastChannel not supported for LiveDataStatusBar')
    }

    // Also poll REST API as fallback
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/market-data/live-view-stats')
        const result = await response.json()
        if (result.success && result.stats) {
          setStats(result.stats)
        }
      } catch (err) {
        // Silently fail - WS will provide updates
      }
    }

    fetchStats()
    const interval = setInterval(fetchStats, 5000)

    return () => {
      if (bc) bc.close()
      clearInterval(interval)
    }
  }, [])

  const livePercent = stats.live_data_percent?.toFixed(1) || 0
  const isLiveGood = stats.symbols_with_live >= 20
  const isAlgoReady = stats.algo_ready

  return (
    <div className="live-data-status-bar">
      <div className="status-item live-data">
        <span className={`status-indicator ${isLiveGood ? 'good' : 'warning'}`}>
          {isLiveGood ? '🟢' : '🟡'}
        </span>
        <span className="status-label">Live Data:</span>
        <span className="status-value">
          {stats.symbols_with_live || 0} / {stats.total_symbols || 0}
        </span>
        <span className="status-percent">({livePercent}%)</span>
      </div>

      <div className="status-divider">|</div>

      <div className="status-item algo-ready">
        <span className={`status-indicator ${isAlgoReady ? 'good' : 'blocked'}`}>
          {isAlgoReady ? '🟢' : '🔴'}
        </span>
        <span className="status-label">Algo:</span>
        <span className={`status-value ${isAlgoReady ? 'ready' : 'blocked'}`}>
          {isAlgoReady ? 'READY' : 'BLOCKED'}
        </span>
      </div>

      {!isAlgoReady && stats.algo_reason && (
        <div className="status-reason" title={stats.algo_reason}>
          <span className="reason-text">
            {stats.algo_reason.length > 50 
              ? stats.algo_reason.substring(0, 50) + '...' 
              : stats.algo_reason}
          </span>
        </div>
      )}

      <div className="status-details">
        <span className="detail-item" title="Symbols with bid">
          Bid: {stats.symbols_with_bid || 0}
        </span>
        <span className="detail-item" title="Symbols with ask">
          Ask: {stats.symbols_with_ask || 0}
        </span>
        <span className="detail-item" title="Symbols with last">
          Last: {stats.symbols_with_last || 0}
        </span>
      </div>
    </div>
  )
}

export default LiveDataStatusBar





