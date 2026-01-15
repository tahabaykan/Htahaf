import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import PSFALGOBulkActionPanel from '../components/PSFALGOBulkActionPanel'
import PSFALGOSummaryHeader from '../components/PSFALGOSummaryHeader'
import TradingPanelsOverlay from '../components/TradingPanelsOverlay'
import LiveProposalsPanel from '../components/LiveProposalsPanel'
import LiveDataStatusBar from '../components/LiveDataStatusBar'
import TakeProfitLongsTab from '../components/TakeProfitLongsTab'
import TakeProfitShortsTab from '../components/TakeProfitShortsTab'
import './PSFALGOPage.css'

function PSFALGOPage() {
  const [data, setData] = useState([])
  const [bcConnected, setBcConnected] = useState(false)
  const [pollingActive, setPollingActive] = useState(false)
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [overlayPanelType, setOverlayPanelType] = useState('positions')
  const [summaryRefreshTrigger, setSummaryRefreshTrigger] = useState(0)
  const [activeTab, setActiveTab] = useState('positions')

  // RUNALL Engine State
  const [runallState, setRunallState] = useState({
    global_state: 'IDLE',
    cycle_state: 'INIT',
    loop_count: 0,
    loop_running: false,
    dry_run_mode: true,
    last_error: null
  })
  const [runallLoading, setRunallLoading] = useState(false)
  const [runallError, setRunallError] = useState(null)

  // Use BroadcastChannel to receive data from Scanner page (NO WebSocket)
  useEffect(() => {
    let broadcastChannel = null
    let pollingInterval = null

    try {
      broadcastChannel = new BroadcastChannel('market-data')
      setBcConnected(true)
      console.log('✅ PSFALGO: BroadcastChannel connected (Subscriber)')

      broadcastChannel.onmessage = (event) => {
        try {
          const message = event.data
          if (message.type === 'market_data_update') {
            // Update data with new market data from Scanner
            setData(prevData => {
              const dataMap = new Map(prevData.map(item => [item.PREF_IBKR, item]))

              // Update with new data
              message.data.forEach(update => {
                const key = update.PREF_IBKR || update.symbol
                if (key) {
                  dataMap.set(key, { ...dataMap.get(key), ...update })
                }
              })

              return Array.from(dataMap.values())
            })
          }
        } catch (err) {
          console.error('PSFALGO: Error parsing BroadcastChannel message:', err)
        }
      }

      broadcastChannel.onerror = (error) => {
        console.error('PSFALGO: BroadcastChannel error:', error)
        setBcConnected(false)
      }
    } catch (err) {
      console.warn('PSFALGO: BroadcastChannel not supported, falling back to REST polling:', err)
      setBcConnected(false)

      // Fallback: REST polling every 2 seconds
      setPollingActive(true)
      pollingInterval = setInterval(() => {
        fetchMergedData()
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

  // 🟢 FAST PATH - Fetch FAST data (L1 + CSV, no tick-by-tick)
  const fetchMergedData = useCallback(async () => {
    try {
      // Use /fast/all instead of /merged for instant L1 data
      const response = await fetch('/api/market-data/fast/all')
      const result = await response.json()

      if (result.success && result.data && result.data.length > 0) {
        setData(result.data)
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching data:', err)
    }
  }, [])

  // Hard refresh all PSFALGO data
  const refetchAllPSFALGO = useCallback(async () => {
    try {
      // 🟢 FAST PATH - Fetch FAST data
      const mergedResponse = await fetch('/api/market-data/fast/all')
      const mergedResult = await mergedResponse.json()
      if (mergedResult.success && mergedResult.data && mergedResult.data.length > 0) {
        setData(mergedResult.data)
      }

      // Trigger summary header refresh
      setSummaryRefreshTrigger(prev => prev + 1)
    } catch (err) {
      console.error('PSFALGO: Error refetching data:', err)
    }
  }, [])

  // Load data on mount
  useEffect(() => {
    fetchMergedData()
    // Refresh every 5 seconds
    const interval = setInterval(fetchMergedData, 5000)
    return () => clearInterval(interval)
  }, [fetchMergedData])

  // Fetch RUNALL state
  const fetchRunallState = useCallback(async () => {
    try {
      const response = await fetch('/api/psfalgo/state')
      const result = await response.json()

      if (result.success && result.state) {
        setRunallState(result.state)
        setRunallError(null)
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching RUNALL state:', err)
      // Don't set error for network issues - RUNALL might not be initialized yet
    }
  }, [])

  // Poll RUNALL state
  useEffect(() => {
    fetchRunallState()
    const interval = setInterval(fetchRunallState, 4000) // Every 4 seconds
    return () => clearInterval(interval)
  }, [fetchRunallState])

  // Start RUNALL
  const handleStartRunall = async () => {
    setRunallLoading(true)
    setRunallError(null)
    try {
      const response = await fetch('/api/psfalgo/start', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchRunallState()
        setSummaryRefreshTrigger(prev => prev + 1)
      } else {
        setRunallError(result.detail || result.error || 'Failed to start RUNALL')
      }
    } catch (err) {
      console.error('PSFALGO: Error starting RUNALL:', err)
      setRunallError(err.message || 'Failed to start RUNALL')
    } finally {
      setRunallLoading(false)
    }
  }

  // Stop RUNALL
  const handleStopRunall = async () => {
    setRunallLoading(true)
    setRunallError(null)
    try {
      const response = await fetch('/api/psfalgo/stop', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchRunallState()
      } else {
        setRunallError(result.detail || result.error || 'Failed to stop RUNALL')
      }
    } catch (err) {
      console.error('PSFALGO: Error stopping RUNALL:', err)
      setRunallError(err.message || 'Failed to stop RUNALL')
    } finally {
      setRunallLoading(false)
    }
  }

  // Get state badge color
  const getStateBadgeClass = () => {
    switch (runallState.global_state) {
      case 'RUNNING':
        return 'running'
      case 'WAITING':
        return 'waiting'
      case 'ERROR':
        return 'error'
      case 'BLOCKED':
        return 'blocked'
      default:
        return 'idle'
    }
  }

  // Toggle Engine Logic (Mutual Exclusivity)
  const toggleEngine = async (engineName, isChecked) => {
    // Default set if null/undefined
    let currentEngines = runallState.active_engines || ['LT_TRIM', 'KARBOTU', 'ADDNEWPOS_ENGINE', 'MM_ENGINE'];
    let newEngines = [...currentEngines];

    if (isChecked) {
      if (!newEngines.includes(engineName)) newEngines.push(engineName);

      // Mutual Exclusivity: KARBOTU vs REDUCEMORE
      if (engineName === 'KARBOTU') {
        newEngines = newEngines.filter(e => e !== 'REDUCEMORE');
      } else if (engineName === 'REDUCEMORE') {
        newEngines = newEngines.filter(e => e !== 'KARBOTU');
      }
    } else {
      // Allow deselecting any engine
      newEngines = newEngines.filter(e => e !== engineName);
    }

    // Update Local State Optimistically
    setRunallState(prev => ({ ...prev, active_engines: newEngines }));

    // Send to Backend
    try {
      await fetch('/api/psfalgo/set-active-engines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEngines)
      });
      // Do NOT await fetchRunallState immediately to prevent race condition flickering.
      // The optimistic update is enough, the polling will eventually sync it.
    } catch (err) {
      console.error("Failed to set active engines:", err);
      // Revert on error if needed, but for now simple logging
    }
  }

  return (
    <div className="psfalgo-page">
      <header className="psfalgo-header">
        <div className="psfalgo-header-left">
          <Link to="/" className="back-to-scanner-link">
            ← Scanner
          </Link>
          <h1>🤖 PSFALGO - Position Management</h1>
          <Link to="/psfalgo-rules" className="rules-button">
            ⚙️ Set & Check Rules
          </Link>
        </div>
        <div className="psfalgo-header-right">
          <span className={`status-badge ${bcConnected ? 'connected' : 'disconnected'}`}>
            {bcConnected ? '🟢 BC Connected' : pollingActive ? '🔄 Polling' : '🔴 Disconnected'}
          </span>
        </div>
      </header>

      {/* Live Data Status Bar - Shows live_data vs algo_ready */}
      <LiveDataStatusBar />

      {/* RUNALL Control Panel */}
      <div className="runall-control-panel">
        <div className="runall-status">
          <span className={`runall-state-badge ${getStateBadgeClass()}`}>
            {runallState.global_state === 'RUNNING' ? '🟢' :
              runallState.global_state === 'WAITING' ? '🟡' :
                runallState.global_state === 'ERROR' ? '🔴' :
                  runallState.global_state === 'BLOCKED' ? '🟠' : '⚪'}
            {' '}{runallState.global_state}
          </span>
          {runallState.loop_running && (
            <span className="runall-cycle-info">
              Cycle #{runallState.loop_count} | {runallState.cycle_state}
            </span>
          )}
          {runallState.dry_run_mode && (
            <span className="runall-dry-run-badge">DRY-RUN</span>
          )}
        </div>

        <div className="runall-engine-controls" style={{ display: 'flex', gap: '10px', alignItems: 'center', margin: '0 20px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#e0e0e0', fontSize: '0.9em' }}>
            <input
              type="checkbox"
              checked={runallState.active_engines?.includes('LT_TRIM') ?? true}
              onChange={(e) => toggleEngine('LT_TRIM', e.target.checked)}
            />
            LT TRIM
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#e0e0e0', fontSize: '0.9em' }}>
            <input
              type="checkbox"
              checked={runallState.active_engines?.includes('KARBOTU') ?? true}
              onChange={(e) => toggleEngine('KARBOTU', e.target.checked)}
            />
            KARBOTU
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#e0e0e0', fontSize: '0.9em' }}>
            <input
              type="checkbox"
              checked={runallState.active_engines?.includes('REDUCEMORE') ?? false}
              onChange={(e) => toggleEngine('REDUCEMORE', e.target.checked)}
            />
            REDUCEMORE
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#e0e0e0', fontSize: '0.9em' }}>
            <input
              type="checkbox"
              checked={runallState.active_engines?.includes('ADDNEWPOS_ENGINE') ?? true}
              onChange={(e) => toggleEngine('ADDNEWPOS_ENGINE', e.target.checked)}
            />
            ADDNEWPOS
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#e0e0e0', fontSize: '0.9em' }}>
            <input
              type="checkbox"
              checked={runallState.active_engines?.includes('MM_ENGINE') ?? true}
              onChange={(e) => toggleEngine('MM_ENGINE', e.target.checked)}
            />
            MM ENGINE
          </label>
        </div>

        <div className="runall-controls">
          {!runallState.loop_running ? (
            <button
              className="runall-start-btn"
              onClick={handleStartRunall}
              disabled={runallLoading}
            >
              {runallLoading ? '⏳ Starting...' : '▶️ Start RUNALL'}
            </button>
          ) : (
            <button
              className="runall-stop-btn"
              onClick={handleStopRunall}
              disabled={runallLoading}
            >
              {runallLoading ? '⏳ Stopping...' : '⏹️ Stop RUNALL'}
            </button>
          )}

          <Link to="/psfalgo-intentions" className="intentions-link-btn">
            📋 View Intentions
          </Link>
        </div>

        {runallError && (
          <div className="runall-error">
            ⚠️ {runallError}
          </div>
        )}

        {runallState.last_error && (
          <div className="runall-last-error">
            Last Error: {runallState.last_error}
          </div>
        )}
      </div>

      {/* Summary Header */}
      <PSFALGOSummaryHeader onRefresh={summaryRefreshTrigger} />

      {/* Live Proposals Panel - Shows real-time order proposals */}
      <LiveProposalsPanel wsConnected={bcConnected} />

      {/* Tab Navigation */}
      <div className="psfalgo-tabs">
        <button
          className={`psfalgo-tab-btn ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => setActiveTab('positions')}
        >
          Positions
        </button>
        <button
          className={`psfalgo-tab-btn ${activeTab === 'longs' ? 'active' : ''}`}
          onClick={() => setActiveTab('longs')}
        >
          Take Profit Longs
        </button>
        <button
          className={`psfalgo-tab-btn ${activeTab === 'shorts' ? 'active' : ''}`}
          onClick={() => setActiveTab('shorts')}
        >
          Take Profit Shorts
        </button>
      </div>

      <div className="psfalgo-content">
        {activeTab === 'positions' && (
          <PSFALGOBulkActionPanel
            data={data}
            onLedgerUpdate={refetchAllPSFALGO}
            onCycleUpdate={refetchAllPSFALGO}
          />
        )}
        {activeTab === 'longs' && <TakeProfitLongsTab />}
        {activeTab === 'shorts' && <TakeProfitShortsTab />}
      </div>

      {/* Trading Panels Overlay (for Shadow Positions, etc.) */}
      <TradingPanelsOverlay
        isOpen={overlayOpen}
        onClose={() => setOverlayOpen(false)}
        tradingMode={tradingMode}
        panelType={overlayPanelType}
      />
    </div>
  )
}

export default PSFALGOPage

